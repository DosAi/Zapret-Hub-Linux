from __future__ import annotations

import subprocess
import os
import shlex
import sys
from pathlib import Path
from subprocess import CompletedProcess

from zapret_hub.services.logging_service import LoggingManager
from zapret_hub.runtime_env import development_install_root

if sys.platform.startswith("win"):
    import winreg
else:
    winreg = None  # type: ignore[assignment]


class AutostartManager:
    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    APP_NAME = "ZapretHub"
    TASK_NAME = "ZapretHub"
    LEGACY_APP_NAMES = ("Zapret Hub", "zapret_hub")

    def __init__(self, logging: LoggingManager) -> None:
        self.logging = logging

    def is_enabled(self) -> bool:
        if not sys.platform.startswith("win"):
            desktop_file = self._linux_desktop_file()
            try:
                content = desktop_file.read_text(encoding="utf-8")
            except OSError:
                return False
            values: dict[str, str] = {}
            for line in content.splitlines():
                if "=" not in line or line.lstrip().startswith("#"):
                    continue
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
            if values.get("Type") != "Application" or values.get("Hidden", "false").lower() == "true":
                return False
            if values.get("X-GNOME-Autostart-enabled", "true").lower() == "false":
                return False
            try:
                command = shlex.split(values.get("Exec", ""), posix=True)
            except ValueError:
                return False
            if not command:
                return False
            executable = Path(command[0]).expanduser()
            return executable.is_file() and os.access(executable, os.X_OK)
        return self._task_exists() or self._run_entry_exists()

    def set_enabled(self, enabled: bool) -> bool:
        if not sys.platform.startswith("win"):
            return self._set_linux_enabled(enabled)
        command = self._build_command()
        self._remove_legacy_run_entries()
        self._delete_task()
        result = False
        if enabled:
            result = self._create_task(command)
            if not result:
                result = self._set_run_entry(command)
        else:
            result = not self.is_enabled()
        self.logging.log("info", "Windows autostart changed", enabled=enabled, actual=result, command=command if enabled else "")
        return result

    def _set_linux_enabled(self, enabled: bool) -> bool:
        desktop_file = self._linux_desktop_file()
        args = self._build_linux_args()
        command = " ".join(self._desktop_quote(item) for item in args)
        try:
            if enabled:
                desktop_file.parent.mkdir(parents=True, exist_ok=True)
                working_directory = str(development_install_root(__file__))
                desktop_file.write_text(
                    "\n".join(
                        (
                            "[Desktop Entry]",
                            "Type=Application",
                            "Name=Zapret Hub",
                            f"Exec={command}",
                            f"TryExec={args[0]}",
                            f"Path={working_directory}",
                            "Terminal=false",
                            "Hidden=false",
                            "X-GNOME-Autostart-enabled=true",
                            "X-GNOME-Autostart-Delay=2",
                            "X-KDE-autostart-after=panel",
                            "",
                        )
                    ),
                    encoding="utf-8",
                )
                desktop_file.chmod(0o644)
            else:
                desktop_file.unlink(missing_ok=True)
        except OSError as error:
            self.logging.log("warning", "Linux autostart change failed", error=str(error))
            return False
        result = self.is_enabled() == enabled
        self.logging.log("info", "Linux autostart changed", enabled=enabled, actual=result, command=command if enabled else "")
        return result

    def _linux_desktop_file(self) -> Path:
        config_home = str(os.environ.get("XDG_CONFIG_HOME", "")).strip()
        root = Path(config_home).expanduser() if config_home else Path.home() / ".config"
        return root / "autostart" / "zapret-hub.desktop"

    def _build_linux_args(self) -> tuple[str, ...]:
        # The installer-owned launcher remains stable when the virtualenv or
        # Python minor version changes during an application update.
        launcher = Path.home() / ".local" / "bin" / "zapret-hub"
        if launcher.is_file() and os.access(launcher, os.X_OK):
            return (str(launcher), "--autostart-launch")
        project_launcher = development_install_root(__file__) / "scripts" / "run_linux.sh"
        if project_launcher.is_file() and os.access(project_launcher, os.X_OK):
            return (str(project_launcher), "--autostart-launch")
        executable = Path(sys.executable).resolve()
        if executable.name.lower() not in {"python", "python3", "python.exe"} and not executable.name.startswith("python3."):
            return (str(executable), "--autostart-launch")
        return (str(executable), "-m", "zapret_hub.main", "--autostart-launch")

    @staticmethod
    def _desktop_quote(value: str) -> str:
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _build_command(self) -> str:
        executable = Path(sys.executable)
        if executable.suffix.lower() == ".exe" and executable.name.lower() != "python.exe":
            return f'"{executable}" --autostart-launch'
        main_module = Path(__file__).resolve().parents[1] / "main.py"
        return f'"{executable}" "{main_module}" --autostart-launch'

    def _task_exists(self) -> bool:
        if not sys.platform.startswith("win"):
            return False
        proc = self._run_schtasks(["/Query", "/TN", self.TASK_NAME])
        return proc.returncode == 0

    def _run_entry_exists(self) -> bool:
        if winreg is None:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_READ) as key:
                for name in (self.APP_NAME, *self.LEGACY_APP_NAMES):
                    try:
                        value, _ = winreg.QueryValueEx(key, name)
                    except FileNotFoundError:
                        continue
                    if str(value or "").strip():
                        return True
        except FileNotFoundError:
            return False
        return False

    def _create_task(self, command: str) -> bool:
        if not sys.platform.startswith("win"):
            return False
        proc = self._run_schtasks(
            [
                "/Create",
                "/F",
                "/SC",
                "ONLOGON",
                "/RL",
                "HIGHEST",
                "/TN",
                self.TASK_NAME,
                "/TR",
                command,
            ]
        )
        if proc.returncode != 0:
            self.logging.log("warning", "Failed to create autostart task", error=(proc.stderr or proc.stdout or "").strip())
            return False
        return True

    def _delete_task(self) -> None:
        if not sys.platform.startswith("win"):
            return
        self._run_schtasks(["/Delete", "/F", "/TN", self.TASK_NAME])

    def _run_schtasks(self, args: list[str]) -> CompletedProcess[str]:
        proc = subprocess.run(
            ["schtasks", *args],
            capture_output=True,
            text=False,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return CompletedProcess(
            proc.args,
            proc.returncode,
            self._decode_process_output(proc.stdout),
            self._decode_process_output(proc.stderr),
        )

    @staticmethod
    def _decode_process_output(output: bytes | None) -> str:
        if not output:
            return ""
        for encoding in ("utf-8-sig", "cp866", "cp1251", "mbcs"):
            try:
                return output.decode(encoding)
            except UnicodeDecodeError:
                continue
            except LookupError:
                continue
        return output.decode("utf-8", errors="replace")

    def _set_run_entry(self, command: str) -> bool:
        if winreg is None:
            return False
        try:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self.APP_NAME, 0, winreg.REG_SZ, command)
            return self._run_entry_exists()
        except OSError as error:
            self.logging.log("warning", "Failed to create autostart Run entry", error=str(error))
            return False

    def _remove_legacy_run_entries(self) -> None:
        if winreg is None:
            return
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                for name in (self.APP_NAME, *self.LEGACY_APP_NAMES):
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            return
