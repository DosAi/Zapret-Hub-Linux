from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from zapret_hub.services.onboarding_state import onboarding_completed, onboarding_is_update, onboarding_marker
from zapret_hub.services.linux_happ import LinuxHappService
from zapret_hub.services.linux_zapret2 import LinuxZapret2Service, LinuxZapretService
import zapret_hub.services.settings as settings_module
from zapret_hub.services.settings import SettingsManager


class _Storage:
    def __init__(self, data_dir: Path) -> None:
        self.paths = SimpleNamespace(data_dir=data_dir)

    def read_json(self, path: Path, default=None):
        if not path.exists():
            return default
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.mark.parametrize("legacy_version", [1, 2, 3])
def test_legacy_onboarding_marker_is_an_update(tmp_path: Path, legacy_version: int) -> None:
    onboarding_marker(tmp_path, legacy_version).write_text("1", encoding="utf-8")

    assert onboarding_is_update(tmp_path)
    assert not onboarding_completed(tmp_path)


def test_current_onboarding_marker_is_not_an_update(tmp_path: Path) -> None:
    onboarding_marker(tmp_path, 2).write_text("1", encoding="utf-8")
    onboarding_marker(tmp_path).write_text("1", encoding="utf-8")

    assert onboarding_completed(tmp_path)
    assert not onboarding_is_update(tmp_path)


@pytest.mark.parametrize(("system_theme", "expected"), [("dark", "night"), ("light", "light")])
def test_legacy_theme_is_replaced_from_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    system_theme: str,
    expected: str,
) -> None:
    storage = _Storage(tmp_path)
    storage.write_json(tmp_path / "settings.json", {"theme": "oled", "component_selection_initialized": True})
    monkeypatch.setattr(SettingsManager, "_detect_system_theme", lambda _self: system_theme)

    assert SettingsManager(storage).get().theme == expected


def test_current_theme_choice_is_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _Storage(tmp_path)
    storage.write_json(tmp_path / "settings.json", {"theme": "oled", "component_selection_initialized": True})
    (tmp_path / ".theme_defaults_v4").write_text("1", encoding="utf-8")
    monkeypatch.setattr(SettingsManager, "_detect_system_theme", lambda _self: "dark")

    assert SettingsManager(storage).get().theme == "oled"


def test_new_client_defaults_youtube_discord_and_tg_proxy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings_module.sys, "platform", "win32")
    storage = _Storage(tmp_path)
    storage.write_json(
        tmp_path / "components.json",
        [
            {"id": "zapret", "enabled": True, "autostart": False},
            {"id": "tg-ws-proxy", "enabled": True, "autostart": True},
        ],
    )
    monkeypatch.setattr(SettingsManager, "_detect_system_theme", lambda _self: "dark")
    monkeypatch.setattr(SettingsManager, "_detect_system_language", lambda _self: "ru")

    settings = SettingsManager(storage).get()
    assert "tg-ws-proxy" in settings.enabled_component_ids
    assert "youtube" in settings.selected_service_ids
    assert "discord" in settings.selected_service_ids


def test_linux_prefers_installed_classic_zapret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _Storage(tmp_path)
    storage.write_json(
        tmp_path / "settings.json",
        {
            "component_selection_initialized": True,
            "enabled_component_ids": ["zapret2"],
            "selected_runtime_mode": "zapret2",
        },
    )
    (tmp_path / ".theme_defaults_v4").write_text("1", encoding="utf-8")
    monkeypatch.setattr(settings_module.sys, "platform", "linux")
    monkeypatch.setattr(LinuxZapretService, "find_nfqws", lambda _self, root=None: tmp_path / "nfqws")
    monkeypatch.setattr(LinuxZapret2Service, "find_nfqws2", lambda _self, root=None: None)
    monkeypatch.setattr(LinuxHappService, "find_executable", lambda _self: None)

    settings = SettingsManager(storage).get()

    assert settings.enabled_component_ids == ["zapret"]
    assert settings.selected_runtime_mode == "zapret"


def test_linux_keeps_selected_zapret2_when_both_backends_are_installed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _Storage(tmp_path)
    storage.write_json(
        tmp_path / "settings.json",
        {
            "component_selection_initialized": True,
            "enabled_component_ids": ["zapret2"],
            "selected_runtime_mode": "zapret2",
        },
    )
    (tmp_path / ".theme_defaults_v4").write_text("1", encoding="utf-8")
    monkeypatch.setattr(settings_module.sys, "platform", "linux")
    monkeypatch.setattr(LinuxZapretService, "find_nfqws", lambda _self, root=None: tmp_path / "nfqws")
    monkeypatch.setattr(LinuxZapret2Service, "find_nfqws2", lambda _self, root=None: tmp_path / "nfqws2")
    monkeypatch.setattr(LinuxHappService, "find_executable", lambda _self: None)

    settings = SettingsManager(storage).get()

    assert settings.enabled_component_ids == ["zapret2"]
    assert settings.selected_runtime_mode == "zapret2"


def test_linux_preserves_tg_proxy_component_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _Storage(tmp_path)
    storage.write_json(
        tmp_path / "settings.json",
        {
            "component_selection_initialized": True,
            "enabled_component_ids": ["zapret2", "tg-ws-proxy", "goshkow-vpn"],
            "autostart_component_ids": ["tg-ws-proxy"],
            "selected_runtime_mode": "zapret2",
            "selected_service_ids": ["telegram-desktop", "youtube"],
        },
    )
    (tmp_path / ".theme_defaults_v4").write_text("1", encoding="utf-8")
    monkeypatch.setattr(settings_module.sys, "platform", "linux")
    monkeypatch.setattr(LinuxZapretService, "find_nfqws", lambda _self, root=None: tmp_path / "nfqws")
    monkeypatch.setattr(LinuxZapret2Service, "find_nfqws2", lambda _self, root=None: tmp_path / "nfqws2")
    monkeypatch.setattr(LinuxHappService, "find_executable", lambda _self: None)

    settings = SettingsManager(storage).get()

    assert settings.enabled_component_ids == ["zapret2", "tg-ws-proxy"]
    assert settings.autostart_component_ids == ["tg-ws-proxy"]


def test_linux_preserves_happ_as_selected_runtime_when_installed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _Storage(tmp_path)
    storage.write_json(
        tmp_path / "settings.json",
        {
            "component_selection_initialized": True,
            "enabled_component_ids": ["goshkow-vpn"],
            "selected_runtime_mode": "goshkow-vpn",
        },
    )
    (tmp_path / ".theme_defaults_v4").write_text("1", encoding="utf-8")
    monkeypatch.setattr(settings_module.sys, "platform", "linux")
    monkeypatch.setattr(LinuxZapretService, "find_nfqws", lambda _self, root=None: tmp_path / "nfqws")
    monkeypatch.setattr(LinuxZapret2Service, "find_nfqws2", lambda _self, root=None: tmp_path / "nfqws2")
    monkeypatch.setattr(LinuxHappService, "find_executable", lambda _self: tmp_path / "happ")

    settings = SettingsManager(storage).get()

    assert settings.enabled_component_ids == ["goshkow-vpn"]
    assert settings.selected_runtime_mode == "goshkow-vpn"
