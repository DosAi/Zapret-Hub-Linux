from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any

from PySide6.QtCore import QObject, QUrl, QUrlQuery, Signal, Slot, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from zapret_hub.runtime_env import development_install_root


class UninstallBridge(QObject):
    event = Signal(str, str)

    def __init__(self, window: "UninstallWindow", project_root: Path) -> None:
        super().__init__(window)
        self.window = window
        self.project_root = project_root
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "status": "ready",
            "message": "",
            "output": "",
            "appRunning": self._main_app_running(),
        }

    @staticmethod
    def _main_app_running() -> bool:
        current_pid = os.getpid()
        proc_root = Path("/proc")
        try:
            candidates = proc_root.iterdir()
        except OSError:
            return False
        for candidate in candidates:
            if not candidate.name.isdigit() or int(candidate.name) == current_pid:
                continue
            try:
                command = (candidate / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", errors="ignore")
            except OSError:
                continue
            if "zapret_hub.uninstaller" in command:
                continue
            if "zapret_hub.main" in command or "/zapret-hub " in f"{command} ":
                return True
        return False

    def _snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def _set_state(self, **values: Any) -> None:
        with self._lock:
            self._state.update(values)

    @Slot(str, str, result=str)
    def call(self, command: str, raw_payload: str) -> str:
        try:
            payload = json.loads(raw_payload or "null")
            if command == "window.minimize":
                self.window.showMinimized()
                value: Any = None
            elif command == "window.startDrag":
                handle = self.window.windowHandle()
                if handle is not None:
                    handle.startSystemMove()
                value = None
            elif command == "window.close":
                if self._snapshot()["status"] != "running":
                    self.window.close()
                value = None
            elif command == "uninstall.preview":
                self._set_state(appRunning=self._main_app_running())
                value = {
                    **self._snapshot(),
                    "projectRoot": str(self.project_root),
                }
            elif command == "uninstall.status":
                if self._snapshot()["status"] == "ready":
                    self._set_state(appRunning=self._main_app_running())
                value = self._snapshot()
            elif command == "uninstall.run":
                if self._snapshot()["status"] == "running":
                    value = self._snapshot()
                else:
                    options = payload if isinstance(payload, dict) else {}
                    if self._main_app_running():
                        self._set_state(
                            status="ready",
                            appRunning=True,
                            message="Close the main Zapret Hub window before uninstalling.",
                        )
                        return json.dumps({"value": self._snapshot()}, ensure_ascii=False)
                    self._set_state(status="running", message="", output="")
                    threading.Thread(
                        target=self._run_uninstaller,
                        args=(bool(options.get("removeHapp")), bool(options.get("purgeData"))),
                        daemon=True,
                        name="zapret-hub-uninstaller",
                    ).start()
                    value = self._snapshot()
            else:
                raise ValueError(f"Unsupported uninstaller command: {command}")
            return json.dumps({"value": value}, ensure_ascii=False)
        except Exception as error:
            return json.dumps({"error": str(error)}, ensure_ascii=False)

    def _run_uninstaller(self, remove_happ: bool, purge_data: bool) -> None:
        command = [str(self.project_root / "scripts" / "uninstall_linux.sh"), "--cli"]
        if remove_happ:
            command.append("--remove-happ")
        if purge_data:
            command.append("--purge-data")
        try:
            completed = subprocess.run(
                command,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
            if completed.returncode == 0:
                self._set_state(status="done", message="", output=output)
            else:
                self._set_state(
                    status="error",
                    message=output or f"Uninstaller exited with code {completed.returncode}",
                    output=output,
                )
        except Exception as error:
            self._set_state(status="error", message=str(error), output="")


class UninstallWindow(QMainWindow):
    def __init__(self, project_root: Path) -> None:
        super().__init__()
        self.setWindowTitle("Zapret Hub — Uninstall")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(820, 520)

        self.view = QWebEngineView(self)
        self.view.setFixedSize(820, 520)
        self.view.page().setBackgroundColor(QColor(Qt.GlobalColor.transparent))
        self.view.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        self.setCentralWidget(self.view)

        self.bridge = UninstallBridge(self, project_root)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        page_url = QUrl.fromLocalFile(str((project_root / "web_ui" / "dist" / "index.html").resolve()))
        query = QUrlQuery()
        query.addQueryItem("uninstall", "1")
        query.addQueryItem("theme", "aurora")
        page_url.setQuery(query)
        self.view.setUrl(page_url)


def main() -> int:
    if not sys.platform.startswith("linux"):
        print("The graphical uninstaller supports Linux only.", file=sys.stderr)
        return 1
    project_root = development_install_root(__file__)
    app = QApplication(sys.argv)
    app.setApplicationName("Zapret Hub Uninstaller")
    icon_path = project_root / "ui_assets" / "icons" / "app.png"
    if icon_path.is_file():
        icon = QIcon(str(icon_path))
        app.setWindowIcon(icon)
    window = UninstallWindow(project_root)
    if not app.windowIcon().isNull():
        window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
