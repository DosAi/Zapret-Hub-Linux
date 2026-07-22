from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Callable


class MarketplaceError(RuntimeError):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class DownloadJob:
    id: str
    slug: str
    version_id: int | None = None
    title: str = ""
    compatibility: str = "zapret"
    author: str = ""
    summary: str = ""
    icon_url: str = ""
    project_url: str = ""
    status: str = "queued"  # queued|downloading|paused|installing|done|error|cancelled
    progress: float = 0.0
    bytes_done: int = 0
    bytes_total: int = 0
    message: str = ""
    error: str = ""


@dataclass
class MarketplaceService:
    """Public Marketplace API client + sequential download queue."""

    BASE_URL = "https://goshkow.ru/api/marketplace/v1"
    USER_AGENT = "Zapret-Hub"
    CONNECT_DEADLINE_SEC = 15.0
    DOWNLOAD_STALL_SEC = 45.0
    DOWNLOAD_WALL_SEC = 300.0

    storage_paths: Any
    logging: Any
    mods: Any | None = None
    mods2: Any | None = None
    on_event: Callable[[str, dict[str, Any]], None] | None = None

    _device_id: str = ""
    _jobs: list[DownloadJob] = field(default_factory=list, init=False, repr=False)
    _worker: threading.Thread | None = field(default=None, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _wake: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _busy: bool = field(default=False, init=False, repr=False)
    _active_id: str = field(default="", init=False, repr=False)
    _cancel_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _pause_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _update_cache: dict[str, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _dismissals: dict[str, str] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self._device_id = self._load_or_create_device_id()
        self._dismissals = self._load_dismissals()
        self._ensure_worker()

    def _emit(self, name: str, payload: dict[str, Any]) -> None:
        if self.on_event is None:
            return
        try:
            self.on_event(name, payload)
        except Exception:
            pass

    def _log(self, level: str, message: str, **fields: Any) -> None:
        try:
            self.logging.log(level, message, **fields)
        except Exception:
            pass

    def _device_path(self) -> Path:
        return Path(self.storage_paths.data_dir) / "marketplace_device_id.txt"

    def _load_or_create_device_id(self) -> str:
        path = self._device_path()
        try:
            if path.exists():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except Exception:
            pass
        value = str(uuid.uuid4())
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        except Exception:
            pass
        return value

    def _dismissals_path(self) -> Path:
        return Path(self.storage_paths.data_dir) / "marketplace_update_dismissals.json"

    def _load_dismissals(self) -> dict[str, str]:
        path = self._dismissals_path()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items() if str(k).strip() and str(v).strip()}
        except Exception:
            pass
        return {}

    def _save_dismissals(self) -> None:
        path = self._dismissals_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._dismissals, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as error:
            self._log("warning", "Failed to save marketplace dismissals", error=str(error))

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        parts = [int(p) for p in re.findall(r"\d+", str(value or ""))]
        return tuple(parts) if parts else (0,)

    def _is_newer(self, latest: str, current: str) -> bool:
        return self._version_tuple(latest) > self._version_tuple(current)

    def _list_marketplace_mods(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for manager, compatibility in ((self.mods, "zapret"), (self.mods2, "zapret2")):
            if manager is None:
                continue
            try:
                installed = manager.list_installed()
            except Exception:
                continue
            for item in installed:
                slug = str(getattr(item, "marketplace_slug", "") or "").strip()
                if not slug:
                    continue
                rows.append(
                    {
                        "modId": item.id,
                        "slug": slug,
                        "title": item.name or slug,
                        "author": item.author or "",
                        "summary": item.description or "",
                        "iconUrl": str(getattr(item, "icon_url", "") or ""),
                        "projectUrl": str(getattr(item, "source_url", "") or ""),
                        "compatibility": compatibility,
                        "currentVersion": str(item.version or ""),
                    }
                )
        return rows

    def fetch_latest(self, slug: str, *, lang: str = "ru") -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            f"/projects/{urllib.parse.quote(slug)}/latest",
            query={"lang": lang if lang in {"ru", "en"} else "ru"},
            timeout=12,
        )
        return {
            "version": str(payload.get("version") or ""),
            "compatibility": str(payload.get("compatibility") or "zapret"),
            "changelog": str(payload.get("changelog") or ""),
            "versionId": int(payload.get("id") or payload.get("version_id") or 0) or None,
        }

    def check_updates(self, *, lang: str = "ru") -> dict[str, Any]:
        """Compare installed marketplace mods with /latest. Fast sequential checks."""
        installed = self._list_marketplace_mods()
        updates: list[dict[str, Any]] = []
        notify: list[dict[str, Any]] = []
        for item in installed:
            slug = item["slug"]
            try:
                latest = self.fetch_latest(slug, lang=lang)
            except Exception as error:
                self._log("warning", "Marketplace update check failed", slug=slug, error=str(error))
                continue
            latest_version = str(latest.get("version") or "")
            current = str(item.get("currentVersion") or "")
            if not latest_version or not self._is_newer(latest_version, current):
                self._update_cache.pop(slug, None)
                continue
            row = {
                **item,
                "latestVersion": latest_version,
                "changelog": str(latest.get("changelog") or ""),
                "versionId": latest.get("versionId"),
                "compatibility": str(latest.get("compatibility") or item.get("compatibility") or "zapret"),
            }
            # Prefer cached cover / remote from project if local icon is empty.
            if not row.get("iconUrl"):
                try:
                    detail = self.get_project(slug, lang=lang)
                    project = detail.get("project") if isinstance(detail.get("project"), dict) else {}
                    row["iconUrl"] = str(project.get("iconUrl") or "")
                    row["projectUrl"] = row.get("projectUrl") or str(project.get("projectUrl") or "")
                    row["summary"] = row.get("summary") or str(project.get("summary") or "")
                    row["author"] = row.get("author") or str(project.get("author") or "")
                    row["title"] = row.get("title") or str(project.get("title") or slug)
                except Exception:
                    pass
            updates.append(row)
            self._update_cache[slug] = row
            dismissed = str(self._dismissals.get(slug) or "")
            if not dismissed or self._is_newer(latest_version, dismissed):
                notify.append(row)
        # Drop cache entries for mods no longer installed.
        alive = {item["slug"] for item in installed}
        for slug in list(self._update_cache):
            if slug not in alive:
                self._update_cache.pop(slug, None)
        return {"ok": True, "updates": updates, "notify": notify}

    def updates_status(self) -> dict[str, Any]:
        return {"ok": True, "updates": list(self._update_cache.values())}

    def dismiss_updates(self, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Remember dismissed latest versions so the modal stays quiet until a newer release."""
        rows = items if isinstance(items, list) else []
        if not rows:
            # Dismiss everything currently cached as available.
            rows = list(self._update_cache.values())
        for item in rows:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug") or "").strip()
            version = str(item.get("latestVersion") or item.get("version") or "").strip()
            if not slug or not version:
                continue
            previous = str(self._dismissals.get(slug) or "")
            if not previous or self._is_newer(version, previous):
                self._dismissals[slug] = version
        self._save_dismissals()
        return {"ok": True, "dismissals": dict(self._dismissals)}

    def clear_update(self, slug: str) -> None:
        slug = str(slug or "").strip()
        if not slug:
            return
        self._update_cache.pop(slug, None)
        self._dismissals.pop(slug, None)
        self._save_dismissals()

    def _remove_existing_by_slug(self, slug: str, *, compatibility: str) -> None:
        slug = str(slug or "").strip()
        if not slug:
            return
        if compatibility == "zapret2" and self.mods2 is not None:
            for item in list(self.mods2.list_installed()):
                if str(getattr(item, "marketplace_slug", "") or "") == slug or item.id == slug:
                    try:
                        self.mods2.remove(item.id)
                    except Exception as error:
                        self._log("warning", "Failed to replace Zapret2 marketplace mod", slug=slug, error=str(error))
            return
        if self.mods is not None:
            for item in list(self.mods.list_installed()):
                if str(getattr(item, "marketplace_slug", "") or "") == slug or item.id == slug:
                    try:
                        self.mods.remove(item.id)
                    except Exception as error:
                        self._log("warning", "Failed to replace marketplace mod", slug=slug, error=str(error))

    def remove_installed(self, slug: str) -> dict[str, Any]:
        slug = str(slug or "").strip()
        if not slug:
            raise MarketplaceError("invalid_slug", "Empty slug")
        removed: list[str] = []
        for manager in (self.mods, self.mods2):
            if manager is None:
                continue
            for item in list(manager.list_installed()):
                if str(getattr(item, "marketplace_slug", "") or "").strip() != slug:
                    continue
                manager.remove(item.id)
                removed.append(str(item.id))
        self.clear_update(slug)
        return {"ok": True, "slug": slug, "removed": removed}

    def device_id(self) -> str:
        return self._device_id

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": self.USER_AGENT,
            "X-Zapret-Device": self._device_id,
        }
        token = str(os.environ.get("ZAPRET_HUB_MARKETPLACE_TOKEN", "") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    @staticmethod
    def _run_with_deadline(func, *, timeout: float):
        """Hard wall-clock deadline without ThreadPoolExecutor shutdown(wait=True) freeze."""
        box: dict[str, object] = {}
        errors: list[BaseException] = []
        done = threading.Event()

        def _target() -> None:
            try:
                box["value"] = func()
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
            finally:
                done.set()

        thread = threading.Thread(target=_target, name="zapret-hub-marketplace-net", daemon=True)
        thread.start()
        deadline = time.monotonic() + max(0.1, float(timeout))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MarketplaceError(
                    "timeout",
                    "Не удалось подключиться к goshkow.ru за 15 секунд. Проверьте сеть и попробуйте снова.",
                )
            if done.wait(timeout=min(0.25, remaining)):
                break
        if errors:
            raise errors[0]
        return box.get("value")

    @staticmethod
    def _friendly_network_message(error: BaseException) -> str:
        if isinstance(error, MarketplaceError):
            text = str(error).strip()
            return text or error.code
        if isinstance(error, TimeoutError):
            return "goshkow.ru не отвечает (таймаут). Проверьте сеть и попробуйте снова."
        if isinstance(error, urllib.error.HTTPError):
            code = int(getattr(error, "code", 0) or 0)
            if code == 404:
                return "Модификация не найдена на goshkow.ru (HTTP 404)."
            if code == 429:
                return "Слишком много запросов к маркетплейсу. Подождите немного."
            if 500 <= code <= 599:
                return f"Маркетплейс goshkow.ru временно недоступен (HTTP {code})."
            return f"Ошибка маркетплейса (HTTP {code})."
        if isinstance(error, (urllib.error.URLError, OSError)):
            return "Не удалось подключиться к маркетплейсу goshkow.ru. Проверьте сеть."
        text = str(error).strip()
        return text or "Сетевая ошибка маркетплейса."

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        timeout: int = 20,
    ) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.BASE_URL}{path}"
        if query:
            cleaned = {k: v for k, v in query.items() if v is not None and str(v) != ""}
            if cleaned:
                url = f"{url}?{urllib.parse.urlencode(cleaned)}"
        data = None
        headers = self._headers(json_body=body is not None)
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())

        def _load() -> dict[str, Any]:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8-sig")
                if not raw.strip():
                    return {"ok": True}
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    return payload
                return {"ok": True, "data": payload}

        try:
            return self._run_with_deadline(_load, timeout=max(float(timeout) + 1.0, self.CONNECT_DEADLINE_SEC))  # type: ignore[return-value]
        except MarketplaceError:
            raise
        except urllib.error.HTTPError as error:
            code = "http_error"
            try:
                err_body = error.read().decode("utf-8-sig")
                parsed = json.loads(err_body)
                if isinstance(parsed, dict) and parsed.get("error"):
                    code = str(parsed.get("error"))
            except Exception:
                pass
            if error.code == 409:
                code = "download_active"
            elif error.code == 429:
                code = "rate_limited"
            raise MarketplaceError(code, self._friendly_network_message(error)) from error
        except Exception as error:
            raise MarketplaceError("network_error", self._friendly_network_message(error)) from error

    def list_projects(
        self,
        *,
        q: str = "",
        compatibility: str = "",
        category: str = "",
        sort: str = "relevance",
        page: int = 1,
        limit: int = 20,
        lang: str = "ru",
    ) -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            "/projects",
            query={
                "q": q,
                "compatibility": compatibility,
                "category": category,
                "sort": sort,
                "page": max(1, int(page)),
                "limit": min(48, max(1, int(limit))),
                "lang": lang if lang in {"ru", "en"} else "ru",
            },
        )
        projects = payload.get("projects") if isinstance(payload.get("projects"), list) else []
        return {
            "ok": bool(payload.get("ok", True)),
            "projects": [self._normalize_card(item) for item in projects if isinstance(item, dict)],
            "total": int(payload.get("total") or 0),
            "page": int(payload.get("page") or page),
            "pages": int(payload.get("pages") or 1),
            "categories": list(payload.get("categories") or ["Игры", "Программы", "Соцсети"]),
        }

    def get_project(self, slug: str, *, lang: str = "ru") -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            f"/projects/{urllib.parse.quote(slug)}",
            query={"lang": lang if lang in {"ru", "en"} else "ru"},
        )
        project = payload.get("project") if isinstance(payload.get("project"), dict) else payload
        if not isinstance(project, dict):
            raise MarketplaceError("not_found", "Project not found")
        card = self._normalize_card(project)
        card["body"] = str(project.get("body") or "")
        card["bodyHtml"] = str(project.get("body_html") or "")
        card["links"] = project.get("links") if isinstance(project.get("links"), list) else []
        card["versions"] = [
            self._normalize_version(item) for item in (payload.get("versions") or []) if isinstance(item, dict)
        ]
        card["dependencies"] = payload.get("dependencies") if isinstance(payload.get("dependencies"), list) else []
        card["screenshots"] = payload.get("screenshots") if isinstance(payload.get("screenshots"), list) else []
        card["commentItems"] = payload.get("comments") if isinstance(payload.get("comments"), list) else []
        return {"ok": True, "project": card}

    def _normalize_card(self, item: dict[str, Any]) -> dict[str, Any]:
        compat = str(item.get("compatibility") or "zapret").lower()
        if compat not in {"zapret", "zapret2"}:
            compat = "zapret"
        updated = item.get("updated_at")
        try:
            updated_ts = int(updated) if updated is not None else 0
        except Exception:
            updated_ts = 0
        return {
            "id": int(item.get("id") or 0),
            "slug": str(item.get("slug") or ""),
            "title": str(item.get("title") or item.get("slug") or "Untitled"),
            "summary": str(item.get("summary") or ""),
            "author": str(item.get("author") or ""),
            "iconUrl": str(item.get("icon_url") or ""),
            "projectUrl": str(item.get("project_url") or ""),
            "apiUrl": str(item.get("api_url") or ""),
            "downloadUrl": str(item.get("download_url") or ""),
            "compatibility": compat,
            "categories": [str(c) for c in (item.get("categories") or []) if c],
            "license": str(item.get("license") or ""),
            "downloads": int(item.get("downloads") or 0),
            "downloadsCompact": str(item.get("downloads_compact") or item.get("downloads") or "0"),
            "likes": int(item.get("likes") or 0),
            "favorites": int(item.get("favorites") or 0),
            "followers": int(item.get("followers") or 0),
            "comments": int(item.get("comments") or 0) if not isinstance(item.get("comments"), list) else len(item.get("comments") or []),
            "featured": bool(item.get("featured")),
            "updatedAt": updated_ts,
            "publishedAt": int(item.get("published_at") or 0) if str(item.get("published_at") or "").isdigit() or isinstance(item.get("published_at"), int) else 0,
        }

    def _normalize_version(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": int(item.get("id") or 0),
            "version": str(item.get("version") or ""),
            "changelog": str(item.get("changelog") or ""),
            "size": int(item.get("size") or 0),
            "sha256": str(item.get("sha256") or ""),
            "downloads": int(item.get("downloads") or 0),
            "publishedAt": item.get("published_at"),
            "compatibility": str(item.get("compatibility") or ""),
        }

    def enqueue_download(
        self,
        slug: str,
        *,
        version_id: int | None = None,
        title: str = "",
        compatibility: str = "",
        author: str = "",
        summary: str = "",
        icon_url: str = "",
        project_url: str = "",
    ) -> dict[str, Any]:
        slug = str(slug or "").strip()
        if not slug:
            raise MarketplaceError("invalid_slug", "Empty slug")
        with self._lock:
            for existing in self._jobs:
                if existing.slug == slug and existing.status in {"queued", "downloading", "paused", "installing"}:
                    self._emit_queue()
                    return {
                        "queued": True,
                        "alreadyQueued": True,
                        "slug": slug,
                        "jobId": existing.id,
                        "pending": [j.slug for j in self._jobs if j.status in {"queued", "downloading", "paused", "installing"}],
                    }
            job = DownloadJob(
                id=str(uuid.uuid4()),
                slug=slug,
                version_id=version_id,
                title=title or slug,
                compatibility=compatibility,
                author=author,
                summary=summary,
                icon_url=icon_url,
                project_url=project_url,
                status="queued",
                message=title or slug,
            )
            self._jobs.append(job)
        self._ensure_worker()
        self._wake.set()
        self._emit_job(job)
        self._emit_queue()
        return {
            "queued": True,
            "slug": slug,
            "jobId": job.id,
            "pending": [j.slug for j in self._jobs if j.status in {"queued", "downloading", "paused", "installing"}],
        }

    def queue_status(self) -> dict[str, Any]:
        with self._lock:
            return self._queue_snapshot()

    def cancel_download(self, slug: str = "", *, job_id: str = "") -> dict[str, Any]:
        slug = str(slug or "").strip()
        job_id = str(job_id or "").strip()
        target: DownloadJob | None = None
        with self._lock:
            target = self._find_job(slug=slug, job_id=job_id)
            if target is None:
                return self._queue_snapshot()
            self._cancel_ids.add(target.id)
            self._pause_ids.discard(target.id)
            if target.status in {"queued", "paused"}:
                target.status = "cancelled"
                target.message = "cancelled"
                self._jobs = [j for j in self._jobs if j.id != target.id]
        self._wake.set()
        self._emit_job(target)
        self._emit_queue()
        return self.queue_status()

    def pause_download(self, slug: str = "", *, job_id: str = "") -> dict[str, Any]:
        slug = str(slug or "").strip()
        job_id = str(job_id or "").strip()
        target: DownloadJob | None = None
        with self._lock:
            target = self._find_job(slug=slug, job_id=job_id)
            if target is None:
                return self._queue_snapshot()
            self._pause_ids.add(target.id)
            if target.status == "queued":
                target.status = "paused"
                target.message = "paused"
        self._wake.set()
        if target is not None:
            self._emit_job(target)
        self._emit_queue()
        return self.queue_status()

    def resume_download(self, slug: str = "", *, job_id: str = "") -> dict[str, Any]:
        slug = str(slug or "").strip()
        job_id = str(job_id or "").strip()
        target: DownloadJob | None = None
        with self._lock:
            target = self._find_job(slug=slug, job_id=job_id)
            if target is None:
                return self._queue_snapshot()
            self._pause_ids.discard(target.id)
            if target.status == "paused":
                target.status = "queued"
                target.message = target.title or target.slug
        self._ensure_worker()
        self._wake.set()
        if target is not None:
            self._emit_job(target)
        self._emit_queue()
        return self.queue_status()

    def reorder_queue(self, ordered_slugs: list[str]) -> dict[str, Any]:
        ordered = [str(item).strip() for item in (ordered_slugs or []) if str(item).strip()]
        with self._lock:
            active = [j for j in self._jobs if j.status in {"downloading", "installing"}]
            paused = [j for j in self._jobs if j.status == "paused"]
            queued = [j for j in self._jobs if j.status == "queued"]
            by_slug = {j.slug: j for j in queued}
            next_queued: list[DownloadJob] = []
            seen: set[str] = set()
            for slug in ordered:
                job = by_slug.get(slug)
                if job is None or slug in seen:
                    continue
                next_queued.append(job)
                seen.add(slug)
            for job in queued:
                if job.slug not in seen:
                    next_queued.append(job)
            self._jobs = [*active, *next_queued, *paused]
        self._emit_queue()
        return self.queue_status()

    def _find_job(self, *, slug: str = "", job_id: str = "") -> DownloadJob | None:
        if job_id:
            for job in self._jobs:
                if job.id == job_id:
                    return job
        if slug:
            for job in self._jobs:
                if job.slug == slug and job.status in {"queued", "downloading", "paused", "installing"}:
                    return job
        return None

    def _job_payload(self, job: DownloadJob) -> dict[str, Any]:
        return {
            "jobId": job.id,
            "slug": job.slug,
            "status": job.status,
            "message": job.message or job.title or job.slug,
            "title": job.title,
            "iconUrl": job.icon_url,
            "compatibility": job.compatibility,
            "progress": float(job.progress),
            "bytesDone": int(job.bytes_done),
            "bytesTotal": int(job.bytes_total),
            "error": job.error,
        }

    def _queue_snapshot(self) -> dict[str, Any]:
        active = next((j for j in self._jobs if j.status in {"downloading", "installing"}), None)
        items = [self._job_payload(j) for j in self._jobs if j.status in {"queued", "downloading", "paused", "installing"}]
        overall = 0.0
        if active and active.bytes_total > 0:
            overall = max(0.0, min(1.0, active.bytes_done / active.bytes_total))
        elif active and active.status == "installing":
            overall = max(0.85, float(active.progress or 0.85))
        elif items:
            overall = 0.02
        return {
            "busy": bool(self._busy),
            "activeSlug": active.slug if active else "",
            "overallProgress": overall,
            "pending": [j["slug"] for j in items],
            "items": items,
        }

    def _emit_job(self, job: DownloadJob) -> None:
        payload = self._job_payload(job)
        payload["pending"] = [j.slug for j in self._jobs if j.status in {"queued", "downloading", "paused", "installing"}]
        self._emit("marketplace.download-progress", payload)

    def _emit_queue(self) -> None:
        self._emit("marketplace.queue", self.queue_status())

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="zapret-hub-marketplace-dl")
            self._worker.start()

    def _worker_loop(self) -> None:
        while True:
            try:
                self._wake.wait(timeout=0.5)
                self._wake.clear()
                job = self._pick_next_job()
                if job is None:
                    continue
                with self._lock:
                    self._busy = True
                    self._active_id = job.id
                    job.status = "downloading"
                    job.progress = 0.01
                    job.message = job.title or job.slug
                self._emit_job(job)
                self._emit_queue()
                try:
                    self._run_job(job)
                    with self._lock:
                        if job.id in self._cancel_ids:
                            job.status = "cancelled"
                            job.message = "cancelled"
                        elif job.id in self._pause_ids or job.status == "paused":
                            job.status = "paused"
                            job.message = "paused"
                            self._pause_ids.add(job.id)
                        elif job.status != "cancelled":
                            job.status = "done"
                            job.progress = 1.0
                    self._emit_job(job)
                except Exception as error:
                    try:
                        code = str(getattr(error, "code", "") or "")
                        friendly = self._friendly_network_message(error)
                    except Exception:
                        code = ""
                        friendly = str(error) or "download_failed"
                    if code == "cancelled" or friendly == "cancelled":
                        job.status = "cancelled"
                        job.message = "cancelled"
                    elif code == "paused" or friendly == "paused":
                        with self._lock:
                            job.status = "paused"
                            job.message = "paused"
                            self._pause_ids.add(job.id)
                    else:
                        job.status = "error"
                        job.error = code or "network_error"
                        job.message = friendly
                        self._log("error", "Marketplace download failed", slug=job.slug, error=friendly)
                    self._emit_job(job)
                finally:
                    with self._lock:
                        self._busy = False
                        self._active_id = ""
                        self._cancel_ids.discard(job.id)
                        if job.status in {"done", "error", "cancelled"}:
                            self._jobs = [j for j in self._jobs if j.id != job.id]
                            self._pause_ids.discard(job.id)
                    self._emit_queue()
                    with self._lock:
                        has_more = any(j.status == "queued" for j in self._jobs)
                    if has_more:
                        self._wake.set()
            except Exception as error:
                self._log("error", "Marketplace download worker crashed", error=str(error))
                with self._lock:
                    self._busy = False
                    self._active_id = ""
                time.sleep(0.4)

    def _pick_next_job(self) -> DownloadJob | None:
        with self._lock:
            for job in self._jobs:
                if job.status == "queued" and job.id not in self._pause_ids and job.id not in self._cancel_ids:
                    return job
            return None

    def _run_job(self, job: DownloadJob) -> None:
        self._raise_if_stopped(job)
        ticket = self._create_ticket(job.slug, version_id=job.version_id)
        self._raise_if_stopped(job)
        filename = str(ticket.get("filename") or f"{job.slug}.zip")
        size = int(ticket.get("size") or 0)
        sha256 = str(ticket.get("sha256") or "").lower().removeprefix("sha256:")
        direct = str(ticket.get("direct_url") or "")
        fallback = str(ticket.get("fallback_url") or "")
        ticket_id = str(ticket.get("ticket") or "")
        temp_dir = Path(self.storage_paths.cache_dir) / "marketplace_downloads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        target = temp_dir / re.sub(r"[^\w.\-]+", "_", filename)
        if target.exists():
            try:
                target.unlink()
            except Exception:
                pass
        job.bytes_total = size
        job.message = filename
        self._emit_job(job)
        try:
            self._download_file(direct, fallback, target, expected_size=size, job=job)
            self._raise_if_stopped(job)
            self._verify_file(target, expected_size=size, expected_sha256=sha256)
            if ticket_id:
                self._complete_ticket(ticket_id, success=True, bytes_sent=target.stat().st_size)
        except Exception:
            if ticket_id:
                try:
                    self._complete_ticket(ticket_id, success=False, bytes_sent=target.stat().st_size if target.exists() else 0)
                except Exception:
                    pass
            raise

        compat = job.compatibility
        title = job.title
        author = job.author
        summary = job.summary
        icon_url = job.icon_url
        project_url = job.project_url
        marketplace_version = ""
        try:
            latest = self.fetch_latest(job.slug)
            marketplace_version = str(latest.get("version") or "")
            if not compat:
                compat = str(latest.get("compatibility") or "zapret")
        except Exception:
            if not compat:
                compat = "zapret"
        if not title or not icon_url or not project_url or not author or not summary:
            try:
                detail = self.get_project(job.slug)
                project = detail.get("project") if isinstance(detail.get("project"), dict) else {}
                title = title or str(project.get("title") or "")
                author = author or str(project.get("author") or "")
                summary = summary or str(project.get("summary") or "")
                icon_url = icon_url or str(project.get("iconUrl") or "")
                project_url = project_url or str(project.get("projectUrl") or "")
                if not compat:
                    compat = str(project.get("compatibility") or compat or "zapret")
            except Exception:
                pass
        self._raise_if_stopped(job)
        job.status = "installing"
        job.progress = max(job.progress, 0.9)
        job.message = filename
        self._emit_job(job)
        installed_id = self._install_zip(
            target,
            compatibility=compat,
            title=title,
            author=author,
            summary=summary,
            icon_url=icon_url,
            project_url=project_url,
            slug=job.slug,
            marketplace_version=marketplace_version,
        )
        self.clear_update(job.slug)
        job.status = "done"
        job.progress = 1.0
        job.message = installed_id or job.slug
        job.compatibility = compat
        self._emit(
            "marketplace.download-progress",
            {
                **self._job_payload(job),
                "modId": installed_id,
                "pending": [j.slug for j in self._jobs if j.id != job.id and j.status in {"queued", "downloading", "paused", "installing"}],
            },
        )

    def _raise_if_stopped(self, job: DownloadJob) -> None:
        with self._lock:
            if job.id in self._cancel_ids:
                raise MarketplaceError("cancelled", "cancelled")
            if job.id in self._pause_ids:
                raise MarketplaceError("paused", "paused")

    def _create_ticket(self, slug: str, *, version_id: int | None) -> dict[str, Any]:
        body: dict[str, Any] = {"slug": slug, "version_id": version_id}
        # Retry a few times if another download_active ticket is still settling.
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                return self._request_json("POST", "/downloads", body=body, timeout=30)
            except MarketplaceError as error:
                last_error = error
                if error.code != "download_active" or attempt >= 3:
                    raise
                time.sleep(1.2 * (attempt + 1))
        raise last_error or MarketplaceError("download_active")

    def _complete_ticket(self, ticket: str, *, success: bool, bytes_sent: int) -> None:
        self._request_json(
            "POST",
            f"/downloads/{urllib.parse.quote(ticket)}/complete",
            body={"success": bool(success), "bytes_sent": int(bytes_sent)},
            timeout=20,
        )

    def _download_file(
        self,
        direct_url: str,
        fallback_url: str,
        target: Path,
        *,
        expected_size: int,
        job: DownloadJob | None = None,
    ) -> None:
        if not direct_url and not fallback_url:
            raise MarketplaceError("no_url", "No download URL in ticket")
        try:
            self._stream_to_file(direct_url, target, resume_from=0, job=job)
            return
        except MarketplaceError:
            raise
        except Exception as direct_error:
            self._log("warning", "Marketplace direct download failed, trying fallback", error=str(direct_error))
            if not fallback_url:
                raise
            already = target.stat().st_size if target.exists() else 0
            # If direct left a partial file, resume via Range; else rewrite.
            self._stream_to_file(
                fallback_url,
                target,
                resume_from=already if already and expected_size and already < expected_size else 0,
                job=job,
            )

    def _stream_to_file(self, url: str, target: Path, *, resume_from: int, job: DownloadJob | None = None) -> None:
        headers = {"User-Agent": self.USER_AGENT, "X-Zapret-Device": self._device_id}
        mode = "wb"
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
            mode = "ab"
        request = urllib.request.Request(url, headers=headers, method="GET")
        # Open + read MUST stay on the same thread. Opening via _run_with_deadline
        # and reading here caused hangs (progress stuck near 0).
        sock_timeout = max(15.0, float(self.DOWNLOAD_STALL_SEC))
        try:
            response = urllib.request.urlopen(request, timeout=sock_timeout)
        except MarketplaceError:
            raise
        except Exception as error:
            raise MarketplaceError("network_error", self._friendly_network_message(error)) from error

        try:
            status = getattr(response, "status", None) or response.getcode()
            if resume_from > 0 and int(status) == 200:
                # Server ignored Range — rewrite to avoid corrupt concat.
                mode = "wb"
                resume_from = 0
            if job is not None and job.bytes_total <= 0:
                try:
                    header_len = int(response.headers.get("Content-Length") or 0)
                except Exception:
                    header_len = 0
                if header_len > 0:
                    job.bytes_total = int(resume_from) + header_len
                    self._emit_job(job)
            done = int(resume_from)
            last_emit = 0.0
            started = time.monotonic()
            last_chunk = started
            with target.open(mode) as handle:
                while True:
                    if job is not None:
                        self._raise_if_stopped(job)
                    now = time.monotonic()
                    if now - started >= self.DOWNLOAD_WALL_SEC:
                        raise MarketplaceError(
                            "timeout",
                            "Загрузка модификации превысила лимит времени. Попробуйте снова.",
                        )
                    if now - last_chunk >= self.DOWNLOAD_STALL_SEC:
                        raise MarketplaceError(
                            "timeout",
                            "Загрузка модификации зависла (нет данных). Проверьте сеть и попробуйте снова.",
                        )
                    try:
                        chunk = response.read(1024 * 256)
                    except TimeoutError as error:
                        raise MarketplaceError(
                            "timeout",
                            "Загрузка модификации зависла (нет данных). Проверьте сеть и попробуйте снова.",
                        ) from error
                    except OSError as error:
                        if "timed out" in str(error).lower():
                            raise MarketplaceError(
                                "timeout",
                                "Загрузка модификации зависла (нет данных). Проверьте сеть и попробуйте снова.",
                            ) from error
                        raise MarketplaceError("network_error", self._friendly_network_message(error)) from error
                    if not chunk:
                        break
                    last_chunk = time.monotonic()
                    handle.write(chunk)
                    done += len(chunk)
                    if job is None:
                        continue
                    job.bytes_done = done
                    if job.bytes_total > 0:
                        job.progress = max(0.01, min(0.89, done / job.bytes_total))
                    else:
                        job.progress = max(0.05, min(0.85, job.progress + 0.01))
                    emit_now = time.monotonic()
                    if emit_now - last_emit >= 0.12:
                        last_emit = emit_now
                        self._emit_job(job)
                        self._emit_queue()
        finally:
            try:
                response.close()
            except Exception:
                pass

    def _verify_file(self, path: Path, *, expected_size: int, expected_sha256: str) -> None:
        actual_size = path.stat().st_size
        if expected_size and actual_size != expected_size:
            path.unlink(missing_ok=True)
            raise MarketplaceError("size_mismatch", f"Size mismatch: {actual_size} != {expected_size}")
        if expected_sha256:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 256)
                    if not chunk:
                        break
                    digest.update(chunk)
            actual = digest.hexdigest().lower()
            if actual != expected_sha256.lower():
                path.unlink(missing_ok=True)
                raise MarketplaceError("checksum_mismatch", "SHA-256 mismatch")

    def _install_zip(
        self,
        zip_path: Path,
        *,
        compatibility: str,
        title: str = "",
        author: str = "",
        summary: str = "",
        icon_url: str = "",
        project_url: str = "",
        slug: str = "",
        marketplace_version: str = "",
    ) -> str:
        """Install via the same filtered ZIP import path as manual mod import."""
        self._remove_existing_by_slug(slug, compatibility=compatibility)
        version = str(marketplace_version or "").strip()
        if compatibility == "zapret2":
            if self.mods2 is None:
                raise MarketplaceError("no_mods2", "Zapret2 mods manager unavailable")
            entry = self.mods2.import_from_path(zip_path)
            local_cover = self._cache_cover_image(Path(entry.path), icon_url)
            try:
                entry = self.mods2.update_metadata(
                    entry.id,
                    name=title.strip() or entry.name,
                    description=summary.strip() or entry.description,
                    author=author.strip() or entry.author,
                    version=version or entry.version,
                    icon_url=local_cover or icon_url,
                    marketplace_slug=slug,
                    source_url=project_url,
                )
                self._verify_installed_entry(self.mods2, entry.id, slug)
            except Exception as error:
                self._rollback_failed_import(self.mods2, entry.id)
                raise MarketplaceError("install_failed", f"Не удалось зарегистрировать модификацию: {error}") from error
            return str(entry.id)
        if self.mods is None:
            raise MarketplaceError("no_mods", "Mods manager unavailable")
        entry = self.mods.import_from_path(str(zip_path))
        local_cover = self._cache_cover_image(Path(entry.path), icon_url)
        try:
            entry = self.mods.update_metadata(
                entry.id,
                name=title.strip() or entry.name,
                description=summary.strip() or entry.description,
                author=author.strip() or entry.author,
                version=version or entry.version,
                icon_url=local_cover or icon_url,
                marketplace_slug=slug,
                source_url=project_url,
            )
            self._verify_installed_entry(self.mods, entry.id, slug)
        except Exception as error:
            self._rollback_failed_import(self.mods, entry.id)
            raise MarketplaceError("install_failed", f"Не удалось зарегистрировать модификацию: {error}") from error
        return str(entry.id)

    @staticmethod
    def _verify_installed_entry(manager: Any, mod_id: str, slug: str) -> None:
        saved = next((item for item in manager.list_installed() if str(item.id) == str(mod_id)), None)
        if saved is None:
            raise RuntimeError("модификация отсутствует в реестре установленных")
        if str(getattr(saved, "marketplace_slug", "") or "").strip() != str(slug or "").strip():
            raise RuntimeError("не сохранена связь с Marketplace")
        if not Path(str(getattr(saved, "path", "") or "")).exists():
            raise RuntimeError("папка модификации не создана")

    def _rollback_failed_import(self, manager: Any, mod_id: str) -> None:
        try:
            manager.remove(mod_id)
        except Exception as rollback_error:
            self._log("warning", "Failed to rollback Marketplace import", mod_id=mod_id, error=str(rollback_error))

    def _cache_cover_image(self, mod_path: Path, icon_url: str) -> str:
        """Download author-uploaded cover into the mod folder; return file:// URI when possible."""
        url = str(icon_url or "").strip()
        if not url.startswith(("http://", "https://")):
            return url
        try:
            mod_path.mkdir(parents=True, exist_ok=True)
            suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
                suffix = ".img"
            target = mod_path / f"zapret-hub-cover{suffix}"
            request = urllib.request.Request(
                url,
                headers={"User-Agent": self.USER_AGENT, "Accept": "image/*,*/*"},
                method="GET",
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                data = response.read()
            if not data or len(data) > 8 * 1024 * 1024:
                return url
            target.write_bytes(data)
            return target.resolve().as_uri()
        except Exception as error:
            self._log("warning", "Marketplace cover cache failed", error=str(error), url=url)
            return url
