from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from zapret_hub.domain import LogEntry
from zapret_hub.services.storage import StorageManager


class LoggingManager:
    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage
        self.log_path = self.storage.paths.logs_dir / "app.log"

    def log(self, level: str, message: str, **context: Any) -> LogEntry:
        entry = LogEntry(
            timestamp=datetime.utcnow().isoformat(),
            level=level.upper(),
            message=message,
            context=context,
        )
        with self.log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        return entry

    def read_entries(self) -> list[LogEntry]:
        if not self.log_path.exists():
            return []
        entries: list[LogEntry] = []
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            entries.append(LogEntry(**payload))
        return entries
