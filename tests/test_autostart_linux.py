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


def test_linux_autostart_prefers_stable_user_launcher(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    launcher = tmp_path / ".local" / "bin" / "zapret-hub"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o755)
    manager = AutostartManager(FakeLogging())

    assert manager.set_enabled(True) is True
    content = (tmp_path / "config" / "autostart" / "zapret-hub.desktop").read_text(encoding="utf-8")
    assert f'Exec="{launcher}" "--autostart-launch"' in content
    assert f"TryExec={launcher}" in content

    launcher.unlink()
    assert manager.is_enabled() is False
