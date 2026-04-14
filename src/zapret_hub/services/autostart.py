from __future__ import annotations

import sys
import winreg
from pathlib import Path

from zapret_hub.services.logging_service import LoggingManager


class AutostartManager:
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "ZapretHub"
    LEGACY_APP_NAMES = ("Zapret Hub", "zapret_hub")

    def __init__(self, logging: LoggingManager) -> None:
        self.logging = logging

    def is_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_READ) as key:
                for name in (self.APP_NAME, *self.LEGACY_APP_NAMES):
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                        if value:
                            return True
                    except FileNotFoundError:
                        continue
                return False
        except FileNotFoundError:
            return False

    def set_enabled(self, enabled: bool) -> None:
        command = self._build_command()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            for name in self.LEGACY_APP_NAMES:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            if enabled:
                winreg.SetValueEx(key, self.APP_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, self.APP_NAME)
                except FileNotFoundError:
                    pass
        self.logging.log("info", "Windows autostart changed", enabled=enabled, command=command if enabled else "")

    def _build_command(self) -> str:
        executable = Path(sys.executable)
        if executable.suffix.lower() == ".exe" and executable.name.lower() != "python.exe":
            return f'"{executable}" --autostart-launch'
        main_module = Path.cwd() / "src" / "zapret_hub" / "main.py"
        return f'"{executable}" "{main_module}" --autostart-launch'
