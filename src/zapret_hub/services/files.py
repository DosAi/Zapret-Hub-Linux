from __future__ import annotations

from pathlib import Path

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
