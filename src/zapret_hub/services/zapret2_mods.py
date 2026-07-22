from __future__ import annotations

from dataclasses import asdict, fields as dc_fields
from datetime import datetime
from pathlib import Path
import re
import shutil
import zipfile

from zapret_hub.domain import InstalledMod
from zapret_hub.services.logging_service import LoggingManager
from zapret_hub.services.settings import SettingsManager
from zapret_hub.services.storage import StorageManager
from zapret_hub.services.orchestrator import zapret2_hub


class Zapret2ModsManager:
    """Zapret2 modifications — separate store + merge from classic Zapret mods.

    Layout:
      {work_root}/mods_zapret2/{id}/
        lists/*.txt   → merged into configs/zapret2/list-hub.txt / ipset-hub.txt
        *.lua         → copied into configs/zapret2/mod_lua/
        zapret-hub-mod.json
    Registry: data/installed_zapret2_mods.json
    Settings: enabled_zapret2_mod_ids
    """

    METADATA_FILENAME = "zapret-hub-mod.json"
    UNKNOWN_AUTHOR = "неизвестен"
    ALLOWED_SUFFIXES = {".txt", ".lua"}
    BLOCKED_SUFFIXES = {
        ".exe",
        ".sys",
        ".dll",
        ".msi",
        ".scr",
        ".com",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".js",
        ".jar",
        ".bin",
    }
    JUNK_TXT_PREFIXES = ("readme", "license", "changelog", "copying", "authors")

    def __init__(
        self,
        storage: StorageManager,
        logging: LoggingManager,
        settings: SettingsManager,
    ) -> None:
        self.storage = storage
        self.logging = logging
        self.settings = settings
        mods2 = getattr(storage.paths, "mods_zapret2_dir", None)
        self.mods_dir = Path(mods2) if mods2 is not None else storage.paths.mods_dir.parent / "mods_zapret2"
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        self._installed_path = storage.paths.data_dir / "installed_zapret2_mods.json"
        if not self._installed_path.exists():
            self.storage.write_json(self._installed_path, [])
        self._cleanup_missing()

    def list_installed(self) -> list[InstalledMod]:
        raw = self.storage.read_json(self._installed_path, default=[]) or []
        allowed = {f.name for f in dc_fields(InstalledMod)}
        result: list[InstalledMod] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                result.append(InstalledMod(**{k: v for k, v in item.items() if k in allowed}))
            except Exception:
                continue
        return result

    def _save(self, installed: list[InstalledMod]) -> None:
        self.storage.write_json(self._installed_path, [asdict(item) for item in installed])

    def _sync_enabled(self, installed: list[InstalledMod] | None = None) -> None:
        items = installed if installed is not None else self.list_installed()
        self.settings.update(enabled_zapret2_mod_ids=sorted(item.id for item in items if item.enabled))

    def _cleanup_missing(self) -> None:
        installed = self.list_installed()
        valid = [item for item in installed if Path(item.path).exists()]
        if len(valid) != len(installed):
            self._save(valid)
            self._sync_enabled(valid)

    def _unique_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", (name or "mod").lower()).strip("-") or "mod"
        existing = {item.id for item in self.list_installed()}
        if base not in existing:
            return base
        idx = 2
        while f"{base}-{idx}" in existing:
            idx += 1
        return f"{base}-{idx}"

    def move(self, mod_id: str, direction: int) -> list[InstalledMod]:
        installed = self.list_installed()
        index = next((i for i, item in enumerate(installed) if item.id == mod_id), -1)
        if index < 0:
            return installed
        target = max(0, min(len(installed) - 1, index + int(direction)))
        if target == index:
            return installed
        item = installed.pop(index)
        installed.insert(target, item)
        self._save(installed)
        self.rebuild_merge()
        return installed

    def reorder(self, ordered_ids: list[str]) -> list[InstalledMod]:
        installed = self.list_installed()
        by_id = {item.id: item for item in installed}
        requested: list[InstalledMod] = []
        seen: set[str] = set()
        for raw_id in ordered_ids:
            mod_id = str(raw_id or "")
            if not mod_id or mod_id in seen or mod_id not in by_id:
                continue
            requested.append(by_id[mod_id])
            seen.add(mod_id)
        ordered: list[InstalledMod] = []
        req_iter = iter(requested)
        for item in installed:
            if item.id in seen:
                ordered.append(next(req_iter))
            else:
                ordered.append(item)
        self._save(ordered)
        self.rebuild_merge()
        return ordered

    def create_empty(self, *, name: str, description: str = "", author: str = UNKNOWN_AUTHOR) -> InstalledMod:
        mod_id = self._unique_id(name or "zapret2-mod")
        target = self.mods_dir / mod_id
        (target / "lists").mkdir(parents=True, exist_ok=True)
        (target / "lists" / "list-general.txt").write_text("", encoding="utf-8")
        (target / "lists" / "ipset-all.txt").write_text("", encoding="utf-8")
        entry = InstalledMod(
            id=mod_id,
            version=datetime.utcnow().strftime("%Y.%m.%d"),
            path=str(target),
            name=name.strip() or mod_id,
            author=author.strip() or self.UNKNOWN_AUTHOR,
            description=description.strip(),
            enabled=False,
            source_type="zapret2_bundle",
            emoji="🧩",
        )
        installed = self.list_installed()
        installed.insert(0, entry)
        self._save(installed)
        self._sync_enabled(installed)
        self.logging.log("info", "Zapret2 mod created", mod_id=mod_id)
        return entry

    def update_metadata(
        self,
        mod_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        author: str | None = None,
        version: str | None = None,
        icon_url: str | None = None,
        marketplace_slug: str | None = None,
        source_url: str | None = None,
    ) -> InstalledMod:
        installed = self.list_installed()
        entry = next(item for item in installed if item.id == mod_id)
        if name is not None:
            entry.name = name
        if description is not None:
            entry.description = description
        if author is not None:
            entry.author = author
        if version is not None:
            entry.version = version
        if icon_url is not None:
            entry.icon_url = str(icon_url or "").strip()
        if marketplace_slug is not None:
            entry.marketplace_slug = str(marketplace_slug or "").strip()
        if source_url is not None:
            entry.source_url = str(source_url or "").strip()
        self._save(installed)
        return entry

    def set_enabled(self, mod_id: str, enabled: bool) -> InstalledMod:
        installed = self.list_installed()
        entry = next(item for item in installed if item.id == mod_id)
        entry.enabled = enabled
        self._save(installed)
        self._sync_enabled(installed)
        self.rebuild_merge()
        self.logging.log("info", "Zapret2 mod state changed", mod_id=mod_id, enabled=enabled)
        return entry

    def remove(self, mod_id: str) -> None:
        installed = [item for item in self.list_installed() if item.id != mod_id]
        self._save(installed)
        self._sync_enabled(installed)
        target = self.mods_dir / mod_id
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        self.rebuild_merge()
        self.logging.log("info", "Zapret2 mod removed", mod_id=mod_id)

    def _is_junk_txt(self, name: str) -> bool:
        stem = Path(name).stem.lower()
        return any(stem == prefix or stem.startswith(f"{prefix}.") or stem.startswith(f"{prefix}-") for prefix in self.JUNK_TXT_PREFIXES)

    def _is_allowed_relative(self, relative: Path) -> bool:
        if relative.is_absolute() or ".." in relative.parts:
            return False
        name = relative.name
        lowered = name.lower()
        if lowered == self.METADATA_FILENAME.lower():
            return True
        if "windivert" in lowered:
            return False
        if "__pycache__" in relative.parts or ".git" in relative.parts:
            return False
        suffix = relative.suffix.lower()
        if suffix in self.BLOCKED_SUFFIXES:
            return False
        if suffix == ".lua":
            return True
        if suffix == ".txt":
            return not self._is_junk_txt(name)
        return False

    def _extract_zip_filtered(self, source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(source, "r") as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                rel = Path(member.filename.replace("\\", "/"))
                if not self._is_allowed_relative(rel):
                    continue
                destination = target / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member, "r") as src, destination.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

    def _copy_tree_filtered(self, source: Path, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        for file_path in source.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(source)
            if not self._is_allowed_relative(rel):
                continue
            destination = target / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, destination)

    def _unwrap_single_root(self, target: Path) -> None:
        children = [p for p in target.iterdir()]
        if len(children) == 1 and children[0].is_dir():
            nested = children[0]
            for item in nested.iterdir():
                shutil.move(str(item), str(target / item.name))
            shutil.rmtree(nested, ignore_errors=True)

    def import_from_path(self, path: str | Path) -> InstalledMod:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(str(source))
        name = source.stem if source.is_file() else source.name
        mod_id = self._unique_id(name)
        target = self.mods_dir / mod_id
        if target.exists():
            shutil.rmtree(target)
        if source.is_file() and source.suffix.lower() == ".zip":
            self._extract_zip_filtered(source, target)
            self._unwrap_single_root(target)
        elif source.is_dir():
            self._copy_tree_filtered(source, target)
        else:
            target.mkdir(parents=True, exist_ok=True)
            lists = target / "lists"
            lists.mkdir(exist_ok=True)
            if source.suffix.lower() == ".lua":
                shutil.copy2(source, target / source.name)
            elif source.suffix.lower() == ".txt":
                shutil.copy2(source, lists / source.name)
            else:
                raise ValueError("Unsupported Zapret 2 mod file type.")
        entry = InstalledMod(
            id=mod_id,
            version=datetime.utcnow().strftime("%Y.%m.%d"),
            path=str(target),
            name=name,
            author=self.UNKNOWN_AUTHOR,
            enabled=True,
            source_type="zapret2_bundle",
            emoji="📦",
        )
        installed = self.list_installed()
        installed.insert(0, entry)
        self._save(installed)
        self._sync_enabled(installed)
        self.rebuild_merge()
        self.logging.log("info", "Zapret2 mod imported", mod_id=mod_id, source=str(source))
        return entry

    def import_from_paths(self, paths: list[str] | list[Path]) -> InstalledMod:
        if not paths:
            raise ValueError("No files selected")
        first = Path(paths[0])
        name = first.stem if len(paths) == 1 else f"zapret2-mod-{datetime.utcnow().strftime('%H%M%S')}"
        mod_id = self._unique_id(name)
        target = self.mods_dir / mod_id
        lists = target / "lists"
        lists.mkdir(parents=True, exist_ok=True)
        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                continue
            if path.suffix.lower() == ".lua":
                shutil.copy2(path, target / path.name)
            elif path.suffix.lower() == ".txt":
                shutil.copy2(path, lists / path.name)
            elif path.suffix.lower() == ".zip":
                self._extract_zip_filtered(path, target)
                self._unwrap_single_root(target)
            else:
                continue
        entry = InstalledMod(
            id=mod_id,
            version=datetime.utcnow().strftime("%Y.%m.%d"),
            path=str(target),
            name=name,
            author=self.UNKNOWN_AUTHOR,
            enabled=True,
            source_type="zapret2_bundle",
            emoji="📦",
        )
        installed = self.list_installed()
        installed.insert(0, entry)
        self._save(installed)
        self._sync_enabled(installed)
        self.rebuild_merge()
        return entry

    def export_mod(self, mod_id: str, target_dir: str | Path) -> Path:
        entry = next(item for item in self.list_installed() if item.id == mod_id)
        source = Path(entry.path)
        destination = Path(target_dir)
        if destination.suffix.lower() == ".zip":
            zip_path = destination
            zip_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            destination.mkdir(parents=True, exist_ok=True)
            zip_path = destination / f"{entry.id}-{entry.version}.zip"
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in source.rglob("*"):
                if not file_path.is_file():
                    continue
                rel = file_path.relative_to(source)
                if not self._is_allowed_relative(rel):
                    continue
                archive.write(file_path, arcname=str(rel.as_posix()))
        return zip_path

    def rebuild_merge(self) -> None:
        # Custom mods first (higher), marketplace last (below hub/vanilla lines).
        enabled = [item for item in self.list_installed() if item.enabled]
        custom = [item for item in enabled if not str(getattr(item, "marketplace_slug", "") or "").strip()]
        marketplace = [item for item in enabled if str(getattr(item, "marketplace_slug", "") or "").strip()]
        roots = [Path(item.path) for item in [*custom, *marketplace]]
        zapret2_hub.merge_mod_overlays(self.storage.paths.configs_dir, roots)
