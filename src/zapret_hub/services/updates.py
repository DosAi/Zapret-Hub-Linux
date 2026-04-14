from __future__ import annotations

from datetime import datetime

from zapret_hub.domain import UpdateInfo
from zapret_hub.services.logging_service import LoggingManager
from zapret_hub.services.storage import StorageManager


class UpdatesManager:
    def __init__(self, storage: StorageManager, logging: LoggingManager) -> None:
        self.storage = storage
        self.logging = logging

    def check_updates(self) -> list[UpdateInfo]:
        cache_file = self.storage.paths.cache_dir / "mods_index.json"
        cache_stamp = datetime.fromtimestamp(cache_file.stat().st_mtime).isoformat() if cache_file.exists() else "missing"
        updates = [
            UpdateInfo(
                target="application",
                current_version="1.0.0",
                latest_version="1.0.0",
                status="up-to-date",
            ),
            UpdateInfo(
                target="mods-index",
                current_version=cache_stamp,
                latest_version=cache_stamp,
                status="ready",
                changelog="Local sample index loaded",
            ),
        ]
        self.logging.log("info", "Update check completed", items=len(updates))
        return updates
