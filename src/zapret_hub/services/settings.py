from __future__ import annotations

import locale
import re
import sys
from dataclasses import asdict

from zapret_hub.domain import AppSettings
from zapret_hub.services.service_catalog import SERVICE_PRESET_IDS
from zapret_hub.services.storage import StorageManager

if sys.platform.startswith("win"):
    import winreg


class SettingsManager:
    def __init__(self, storage: StorageManager) -> None:
        self.storage = storage
        self._settings_path = self.storage.paths.data_dir / "settings.json"
        self._settings = self.load()

    def load(self) -> AppSettings:
        raw = self.storage.read_json(self._settings_path, default={}) or {}
        allowed = {field.name for field in AppSettings.__dataclass_fields__.values()}
        raw = {key: value for key, value in raw.items() if key in allowed}
        settings = AppSettings(**raw)
        changed = False

        # первый запуск берёт дефолты из components.json
        if not bool(raw.get("component_selection_initialized", False)):
            components_raw = self.storage.read_json(self.storage.paths.data_dir / "components.json", default=[]) or []
            if isinstance(components_raw, list):
                enabled_defaults: list[str] = []
                autostart_defaults: list[str] = []
                for item in components_raw:
                    if not isinstance(item, dict):
                        continue
                    cid = str(item.get("id", "")).strip()
                    if not cid:
                        continue
                    if bool(item.get("enabled", False)):
                        enabled_defaults.append(cid)
                    if bool(item.get("autostart", False)):
                        autostart_defaults.append(cid)
                settings.enabled_component_ids = enabled_defaults
                settings.autostart_component_ids = autostart_defaults
            settings.component_selection_initialized = True
            changed = True

        if not raw.get("language"):
            settings.language = self._detect_system_language()
            changed = True

        if raw.get("theme") == "midnight":
            settings.theme = "night"
            changed = True

        if raw.get("theme") not in ("night", "midnight", "dark", "oled", "light", "light blue"):
            settings.theme = "oled"
            changed = True

        if raw.get("zapret_ipset_mode") not in {"loaded", "none", "any"}:
            settings.zapret_ipset_mode = "loaded"
            changed = True

        if raw.get("zapret_game_filter_mode") == "all":
            settings.zapret_game_filter_mode = "tcpudp"
            changed = True
        elif raw.get("zapret_game_filter_mode") == "auto":
            settings.zapret_game_filter_mode = "disabled"
            changed = True
        elif raw.get("zapret_game_filter_mode") not in {"disabled", "tcp", "udp", "tcpudp"}:
            settings.zapret_game_filter_mode = "disabled"
            changed = True

        normalized_udp_exclude = self._normalize_port_ranges(raw.get("zapret_udp_exclude_ports", settings.zapret_udp_exclude_ports))
        if normalized_udp_exclude != str(settings.zapret_udp_exclude_ports or ""):
            settings.zapret_udp_exclude_ports = normalized_udp_exclude
            changed = True

        if raw.get("zapret_gaming_set") not in {
            "base",
            "base-wide-stun",
            "wide-stun-base",
            "stun-wide-base",
            "stun-wide-base-local-exclude",
            "udp-first",
            "tcp-first",
            "stun-between",
        }:
            settings.zapret_gaming_set = "stun-wide-base"
            changed = True

        if raw.get("selected_runtime_mode") not in {"zapret", "goshkow-vpn"}:
            settings.selected_runtime_mode = "zapret"
            changed = True

        if raw.get("goshkow_vpn_routing_mode") not in {"global", "blacklist", "whitelist"}:
            settings.goshkow_vpn_routing_mode = "global"
            changed = True

        if raw.get("goshkow_vpn_rules_mode") not in {"blacklist", "whitelist"}:
            settings.goshkow_vpn_rules_mode = "blacklist"
            changed = True

        if raw.get("goshkow_vpn_system_proxy_mode") not in {"clear", "set", "unchanged", "pac"}:
            settings.goshkow_vpn_system_proxy_mode = "pac"
            changed = True

        selected_service_ids = raw.get("selected_service_ids", [])
        if not isinstance(selected_service_ids, list):
            settings.selected_service_ids = []
            changed = True
        else:
            service_migrations = {
                "steam": "clouds",
                "twitch": "fortnite",
                "roblox": "gaming",
                "tiktok": "ai",
                "instagram": "ubisoft",
            }
            migrated_service_ids = [
                service_migrations.get(str(item).strip(), str(item).strip())
                for item in selected_service_ids
            ]
            normalized_service_ids = [item for item in migrated_service_ids if item in SERVICE_PRESET_IDS]
            if normalized_service_ids != list(settings.selected_service_ids):
                settings.selected_service_ids = normalized_service_ids
                changed = True

        if changed:
            self.storage.write_json(self._settings_path, asdict(settings))
        return settings

    def get(self) -> AppSettings:
        return self._settings

    def reload(self) -> AppSettings:
        self._settings = self.load()
        return self._settings

    def update(self, **changes: object) -> AppSettings:
        if "zapret_udp_exclude_ports" in changes:
            changes["zapret_udp_exclude_ports"] = self._normalize_port_ranges(changes.get("zapret_udp_exclude_ports", ""))
        for key, value in changes.items():
            setattr(self._settings, key, value)
        self.save()
        return self._settings

    def save(self) -> None:
        self.storage.write_json(self._settings_path, asdict(self._settings))

    def _detect_system_language(self) -> str:
        try:
            locale_name = (locale.getdefaultlocale()[0] or "").lower()  # type: ignore[call-arg]
        except Exception:
            locale_name = ""
        return "ru" if locale_name.startswith("ru") else "en"

    def _normalize_port_ranges(self, value: object) -> str:
        ranges: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()
        for raw in re.split(r"[\s,;]+", str(value or "")):
            token = raw.strip()
            if not token:
                continue
            if "-" in token:
                left, right = token.split("-", 1)
            else:
                left = right = token
            try:
                start = int(left)
                end = int(right)
            except ValueError:
                continue
            if start > end:
                start, end = end, start
            if start < 1 or end > 65535:
                continue
            item = (start, end)
            if item in seen:
                continue
            seen.add(item)
            ranges.append(item)
        return ",".join(str(start) if start == end else f"{start}-{end}" for start, end in ranges)

    def _detect_system_theme(self) -> str:
        if not sys.platform.startswith("win"):
            return "dark"
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                0,
                winreg.KEY_READ,
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "light" if int(value) == 1 else "dark"
        except Exception:
            return "dark"
