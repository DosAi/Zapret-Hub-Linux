from __future__ import annotations

from pathlib import Path
import re

from zapret_hub.domain.models import FileRecord
from zapret_hub.services.storage import StorageManager


class FilesManager:
    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage
        self.allowed_roots = [
            self.storage.paths.configs_dir,
            self.storage.paths.default_packs_dir,
            self.storage.paths.mods_dir,
            self.storage.paths.merged_runtime_dir,
            self.storage.paths.data_dir,
        ]

    def list_files(self) -> list[FileRecord]:
        records: list[FileRecord] = []
        for root in self.allowed_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    records.append(
                        FileRecord(
                            path=str(path),
                            relative_path=str(path.relative_to(self.storage.paths.install_root)),
                            size=path.stat().st_size,
                        )
                    )
        return sorted(records, key=lambda item: item.relative_path.lower())

    def list_user_collections(self) -> list[dict[str, str]]:
        return [
            {"id": "domains", "title": "Domains", "path": str(self._collection_path("domains"))},
            {"id": "exclude_domains", "title": "Exclude domains", "path": str(self._collection_path("exclude_domains"))},
            {"id": "ips", "title": "IP addresses", "path": str(self._collection_path("ips"))},
        ]

    def read_collection(self, kind: str) -> list[str]:
        values: list[str] = []
        seen: set[str] = set()
        for path in self._collection_source_paths(kind):
            for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                value = raw.strip()
                if not value or value.startswith("#"):
                    continue
                if value in {"domain.example.abc", "203.0.113.113/32"}:
                    continue
                if value in seen:
                    continue
                seen.add(value)
                values.append(value)
        return values

    def write_collection(self, kind: str, values: list[str]) -> None:
        path = self._collection_path(kind)
        self._ensure_collection_file(kind)
        normalized = self.normalize_collection_values(kind, values)
        content = "\n".join(normalized)
        path.write_text(content + ("\n" if normalized else ""), encoding="utf-8")

    def add_collection_values(self, kind: str, raw_text: str) -> list[str]:
        current = self.read_collection(kind)
        incoming = self.normalize_collection_values(kind, self._split_raw_values(kind, raw_text))
        seen = set(current)
        for value in incoming:
            if value in seen:
                continue
            seen.add(value)
            current.append(value)
        self.write_collection(kind, current)
        return current

    def remove_collection_value(self, kind: str, value: str) -> list[str]:
        current = [item for item in self.read_collection(kind) if item != value]
        self.write_collection(kind, current)
        return current

    def normalize_collection_values(self, kind: str, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            value = raw.strip()
            if not value:
                continue
            if kind in {"domains", "exclude_domains"}:
                value = self._normalize_domain(value)
            elif kind == "ips":
                value = self._normalize_ip(value)
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _split_raw_values(self, kind: str, raw_text: str) -> list[str]:
        if kind == "ips":
            parts = re.split(r"[\s,;]+", raw_text.strip())
            return [item for item in parts if item]
        prepared = raw_text.replace("\r", " ").replace("\n", " ")
        parts = re.split(r"[\s,;]+", prepared.strip())
        return [item for item in parts if item]

    def read_text(self, path: str) -> str:
        target = Path(path)
        self._guard(target)
        return target.read_text(encoding="utf-8")

    def write_text(self, path: str, content: str) -> None:
        target = Path(path)
        self._guard(target)
        target.write_text(content, encoding="utf-8")

    def _guard(self, path: Path) -> None:
        resolved = path.resolve()
        if not any(str(resolved).startswith(str(root.resolve())) for root in self.allowed_roots):
            raise ValueError(f"Path is outside allowed roots: {resolved}")

    def _collection_path(self, kind: str) -> Path:
        mapping = {
            "domains": self.storage.paths.configs_dir / "list-general-user.txt",
            "exclude_domains": self.storage.paths.configs_dir / "list-exclude-user.txt",
            "ips": self.storage.paths.configs_dir / "ipset-exclude-user.txt",
        }
        if kind not in mapping:
            raise ValueError(f"Unsupported collection kind: {kind}")
        return mapping[kind]

    def _ensure_collection_file(self, kind: str) -> None:
        path = self._collection_path(kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("", encoding="utf-8")

    def _collection_source_paths(self, kind: str) -> list[Path]:
        self._ensure_collection_file(kind)
        sources: list[Path] = []
        merged_lists = self._latest_merged_lists_dir()
        if merged_lists is not None:
            merged_path = self._merged_collection_path(kind, merged_lists)
            if merged_path.exists():
                sources.append(merged_path)
        else:
            runtime_lists = self.storage.paths.runtime_dir / "zapret-discord-youtube" / "lists"
            runtime_path = self._merged_collection_path(kind, runtime_lists)
            if runtime_path.exists():
                sources.append(runtime_path)
        user_path = self._collection_path(kind)
        if user_path.exists():
            sources.append(user_path)
        return sources

    def _latest_merged_lists_dir(self) -> Path | None:
        merged_root = self.storage.paths.merged_runtime_dir
        if not merged_root.exists():
            return None
        candidates = [
            path / "lists"
            for path in merged_root.glob("active_zapret*")
            if path.is_dir() and (path / "lists").exists()
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda item: item.parent.stat().st_mtime, reverse=True)
        return candidates[0]

    def _merged_collection_path(self, kind: str, lists_dir: Path) -> Path:
        mapping = {
            "domains": lists_dir / "list-general.txt",
            "exclude_domains": lists_dir / "list-exclude.txt",
            "ips": lists_dir / "ipset-exclude.txt",
        }
        return mapping[kind]

    def _normalize_domain(self, value: str) -> str:
        prepared = value.strip().lower()
        if not prepared:
            return ""
        prepared = prepared.replace("https://", "").replace("http://", "")
        prepared = prepared.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].strip()
        prepared = prepared.lstrip(".")
        if prepared.startswith("www."):
            prepared = prepared[4:]
        if not prepared or " " in prepared:
            return ""
        if re.fullmatch(r"[a-z0-9._:-]+", prepared) is None:
            return ""
        return prepared

    def _normalize_ip(self, value: str) -> str:
        prepared = value.strip()
        if not prepared:
            return ""
        if re.fullmatch(r"[0-9a-fA-F:.\/]+", prepared) is None:
            return ""
        return prepared
