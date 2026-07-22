from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import hashlib
import threading
import urllib.request
import zipfile

from zapret_hub.services.marketplace import MarketplaceError, MarketplaceService


def test_version_compare():
    svc = MarketplaceService.__new__(MarketplaceService)
    assert svc._is_newer("1.2.0", "1.1.9")
    assert svc._is_newer("2.0.0", "1.9.9")
    assert not svc._is_newer("1.0.0", "1.0.0")
    assert not svc._is_newer("1.0.0", "1.0.1")


def test_dismiss_until_newer(tmp_path):
    class Paths:
        data_dir = tmp_path
        cache_dir = tmp_path / "cache"

    class Logging:
        def log(self, *a, **k):
            pass

    svc = MarketplaceService(storage_paths=Paths(), logging=Logging(), mods=None, mods2=None)
    svc._update_cache = {
        "youtube-flow": {"slug": "youtube-flow", "latestVersion": "1.1.0", "title": "YT"},
    }
    svc.dismiss_updates([{"slug": "youtube-flow", "latestVersion": "1.1.0"}])
    assert svc._dismissals["youtube-flow"] == "1.1.0"

    # Same latest should not notify.
    svc._update_cache = {
        "youtube-flow": {
            "slug": "youtube-flow",
            "latestVersion": "1.1.0",
            "currentVersion": "1.0.0",
            "title": "YT",
        }
    }
    # Simulate notify filter
    notify = []
    for row in svc._update_cache.values():
        dismissed = svc._dismissals.get(row["slug"], "")
        if not dismissed or svc._is_newer(row["latestVersion"], dismissed):
            notify.append(row)
    assert notify == []

    # Newer release should notify again.
    row = {
        "slug": "youtube-flow",
        "latestVersion": "1.2.0",
        "currentVersion": "1.0.0",
        "title": "YT",
    }
    dismissed = svc._dismissals.get(row["slug"], "")
    assert svc._is_newer(row["latestVersion"], dismissed)


def test_download_queue_completes_download_and_install(monkeypatch, tmp_path: Path) -> None:
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("general-test.bat", "@echo off\n")
    payload = archive_buffer.getvalue()

    class Response:
        status = 200
        headers = {"Content-Length": str(len(payload))}

        def __init__(self) -> None:
            self._offset = 0

        def getcode(self) -> int:
            return self.status

        def read(self, size: int = -1) -> bytes:
            if self._offset >= len(payload):
                return b""
            end = len(payload) if size < 0 else min(len(payload), self._offset + size)
            chunk = payload[self._offset:end]
            self._offset = end
            return chunk

        def close(self) -> None:
            return None

    class Paths:
        data_dir = tmp_path / "data"
        cache_dir = tmp_path / "cache"

    class Logging:
        def log(self, *_args, **_kwargs) -> None:
            return None

    class Mods:
        def __init__(self) -> None:
            self.imported: list[Path] = []
            self.installed: list[SimpleNamespace] = []

        def list_installed(self) -> list[object]:
            return list(self.installed)

        def import_from_path(self, path: str) -> object:
            imported = Path(path)
            self.imported.append(imported)
            installed = tmp_path / "installed" / "market-test"
            installed.mkdir(parents=True, exist_ok=True)
            entry = SimpleNamespace(
                id="market-test",
                path=installed,
                name="Market test",
                description="",
                author="",
                version="1.0.0",
                marketplace_slug="",
            )
            self.installed.append(entry)
            return entry

        def update_metadata(self, mod_id: str, **metadata) -> object:
            entry = next(item for item in self.installed if item.id == mod_id)
            for key, value in metadata.items():
                setattr(entry, key, value)
            return entry

        def remove(self, mod_id: str) -> None:
            self.installed = [item for item in self.installed if item.id != mod_id]

    events: list[tuple[str, dict[str, object]]] = []
    completed = threading.Event()

    def on_event(name: str, event_payload: dict[str, object]) -> None:
        events.append((name, event_payload))
        if name == "marketplace.download-progress" and event_payload.get("status") == "done":
            completed.set()

    mods = Mods()
    service = MarketplaceService(storage_paths=Paths(), logging=Logging(), mods=mods, on_event=on_event)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(
        service,
        "_create_ticket",
        lambda *_args, **_kwargs: {
            "filename": "market-test.zip",
            "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "direct_url": "https://example.test/market-test.zip",
            "fallback_url": "",
            "ticket": "ticket-1",
        },
    )
    monkeypatch.setattr(service, "_complete_ticket", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(service, "fetch_latest", lambda *_args, **_kwargs: {"version": "1.0.0", "compatibility": "zapret"})
    monkeypatch.setattr(service, "get_project", lambda *_args, **_kwargs: {"project": {}})

    queued = service.enqueue_download("market-test", title="Market test", compatibility="zapret")

    assert queued["queued"] is True
    assert completed.wait(3), events
    assert mods.imported
    assert mods.installed[0].marketplace_slug == "market-test"
    assert mods.installed[0].path.exists()
    assert any(name == "marketplace.download-progress" and data.get("status") == "installing" for name, data in events)
    assert any(name == "marketplace.download-progress" and data.get("status") == "done" for name, data in events)


def test_remove_installed_marketplace_mod(tmp_path: Path) -> None:
    class Paths:
        data_dir = tmp_path / "data"
        cache_dir = tmp_path / "cache"

    class Logging:
        def log(self, *_args, **_kwargs) -> None:
            return None

    class Mods:
        def __init__(self) -> None:
            self.installed = [SimpleNamespace(id="mod-1", marketplace_slug="market-test")]

        def list_installed(self) -> list[object]:
            return list(self.installed)

        def remove(self, mod_id: str) -> None:
            self.installed = [item for item in self.installed if item.id != mod_id]

    mods = Mods()
    service = MarketplaceService(storage_paths=Paths(), logging=Logging(), mods=mods)

    result = service.remove_installed("market-test")

    assert result == {"ok": True, "slug": "market-test", "removed": ["mod-1"]}
    assert mods.installed == []


def test_ticket_http_error_uses_verified_public_download(monkeypatch, tmp_path: Path) -> None:
    class Paths:
        data_dir = tmp_path / "data"
        cache_dir = tmp_path / "cache"

    class Logging:
        def log(self, *_args, **_kwargs) -> None:
            return None

    service = MarketplaceService(storage_paths=Paths(), logging=Logging())

    def reject_ticket(*_args, **_kwargs):
        raise MarketplaceError("http_error", "HTTP 403")

    monkeypatch.setattr(service, "_request_json", reject_ticket)
    monkeypatch.setattr(
        service,
        "fetch_latest",
        lambda *_args, **_kwargs: {
            "version": "2.1.0",
            "versionId": 4,
            "size": 123,
            "sha256": "abc123",
        },
    )

    ticket = service._create_ticket("shizapret_mod", version_id=None)

    assert ticket["direct_url"].endswith("/projects/shizapret_mod/download/latest")
    assert ticket["size"] == 123
    assert ticket["sha256"] == "abc123"
    assert ticket["filename"] == "shizapret_mod-2.1.0.zip"


def test_download_tries_absolute_fallback_after_marketplace_error(monkeypatch, tmp_path: Path) -> None:
    service = MarketplaceService.__new__(MarketplaceService)
    calls: list[tuple[str, int]] = []

    def stream(url: str, _target: Path, *, resume_from: int, job=None) -> None:
        del job
        calls.append((url, resume_from))
        if len(calls) == 1:
            raise MarketplaceError("network_error", "CDN rejected request")

    monkeypatch.setattr(service, "_stream_to_file", stream)
    monkeypatch.setattr(service, "_log", lambda *_args, **_kwargs: None)

    service._download_file(
        "https://download.goshkow.ru/file.zip",
        "/zapret-hub/marketplace/download/4",
        tmp_path / "mod.zip",
        expected_size=0,
    )

    assert calls == [
        ("https://download.goshkow.ru/file.zip", 0),
        ("https://goshkow.ru/zapret-hub/marketplace/download/4", 0),
    ]


def test_marketplace_image_uses_content_signature_and_disk_cache(monkeypatch, tmp_path: Path) -> None:
    class Paths:
        data_dir = tmp_path / "data"
        cache_dir = tmp_path / "cache"

    class Logging:
        def log(self, *_args, **_kwargs) -> None:
            return None

    png = b"\x89PNG\r\n\x1a\n" + b"payload"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size: int = -1) -> bytes:
            return png

    calls = 0

    def urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return Response()

    service = MarketplaceService(storage_paths=Paths(), logging=Logging())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    url = "https://goshkow.ru/zapret-hub/marketplace/media/project/2/icon"

    first = service.load_image_data_url(url)
    second = service.load_image_data_url(url)

    assert first == second
    assert first["dataUrl"].startswith("data:image/png;base64,")
    assert calls == 1
