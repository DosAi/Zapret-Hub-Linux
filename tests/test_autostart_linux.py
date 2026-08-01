from __future__ import annotations

from pathlib import Path

from zapret_hub.services.autostart import AutostartManager


class FakeLogging:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def log(self, level: str, message: str, **fields: object) -> None:
        self.events.append((level, message, fields))


def test_linux_autostart_round_trip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    manager = AutostartManager(FakeLogging())

    assert manager.set_enabled(True) is True
    desktop_file = tmp_path / "autostart" / "zapret-hub.desktop"
    content = desktop_file.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "--autostart-launch" in content
    assert manager.is_enabled() is True

    assert manager.set_enabled(False) is True
    assert not desktop_file.exists()
