import argparse
import ctypes
import hashlib
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from zapret_hub.bootstrap import bootstrap_application
from zapret_hub.ui.main_window import MainWindow
from zapret_hub.workers import run_tg_ws_proxy_worker


def _set_windows_app_id() -> None:
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("goshkow.ZapretHub")  # type: ignore[attr-defined]
    except Exception:
        return


def _ensure_admin_windows(argv: list[str]) -> int:
    if not sys.platform.startswith("win"):
        return 0
    try:
        is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return 0
    if is_admin:
        return 0

    params = " ".join(f'"{arg}"' if " " in arg else arg for arg in argv)
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    if result <= 32:
        return 3
    return 2


def _single_instance_key() -> str:
    base = str(sys.executable if getattr(sys, "frozen", False) else __file__)
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:12]
    return f"zapret_hub_{digest}"


def _notify_existing_instance(server_name: str) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if not socket.waitForConnected(220):
        return False
    socket.write(b"SHOW")
    socket.flush()
    socket.waitForBytesWritten(220)
    socket.disconnectFromServer()
    return True


def _create_single_instance_server(server_name: str) -> QLocalServer | None:
    server = QLocalServer()
    if server.listen(server_name):
        return server
    QLocalServer.removeServer(server_name)
    if server.listen(server_name):
        return server
    return None


def _resolve_app_icon_path() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        install_root = Path(sys.executable).resolve().parent
        resource_root = Path(getattr(sys, "_MEIPASS", install_root))
        candidates.extend(
            [
                install_root / "ui_assets" / "icons" / "app.ico",
                resource_root / "ui_assets" / "icons" / "app.ico",
            ]
        )
    candidates.append(Path.cwd() / "ui_assets" / "icons" / "app.ico")
    for path in candidates:
        if path.exists():
            return path
    return None


def run(argv: list[str] | None = None) -> int:
    runtime_argv = list(argv if argv is not None else sys.argv[1:])
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker", choices=["tg-ws-proxy"], default="")
    parser.add_argument("--autostart-launch", action="store_true")
    parser.add_argument("--tg-host", default="127.0.0.1")
    parser.add_argument("--tg-port", type=int, default=1443)
    parser.add_argument("--tg-secret", default="")
    parser.add_argument("--tg-verbose", action="store_true")
    known, _ = parser.parse_known_args(runtime_argv)

    if known.worker == "tg-ws-proxy":
        return run_tg_ws_proxy_worker(
            host=known.tg_host,
            port=known.tg_port,
            secret=known.tg_secret,
            verbose=known.tg_verbose,
        )

    elevate_result = _ensure_admin_windows(runtime_argv)
    if elevate_result in (2, 3):
        return elevate_result

    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Zapret Hub")
    app.setOrganizationName("ZapretHub")
    icon_path = _resolve_app_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    instance_key = _single_instance_key()
    if _notify_existing_instance(instance_key):
        return 0

    context = bootstrap_application()
    window = MainWindow(context)
    server = _create_single_instance_server(instance_key)
    if server is not None:
        def _on_new_connection() -> None:
            while server.hasPendingConnections():
                client = server.nextPendingConnection()
                if client is not None:
                    client.readAll()
                    client.disconnectFromServer()
            window.restore_from_external_launch()
        server.newConnection.connect(_on_new_connection)
        app._single_instance_server = server  # type: ignore[attr-defined]
        app._single_instance_window = window  # type: ignore[attr-defined]
    def _cleanup_before_quit() -> None:
        try:
            context.processes.stop_all()
        except Exception:
            pass
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
    app.aboutToQuit.connect(_cleanup_before_quit)
    settings = context.settings.get()
    # держим автозапуск в реестре в актуальном состоянии
    context.autostart.set_enabled(bool(settings.autostart_windows))
    if known.autostart_launch:
        context.settings.update(start_in_tray=True)
        if settings.auto_run_components:
            context.processes.start_enabled_components()
        window.hide()
    else:
        window.show()
        if settings.auto_run_components:
            context.processes.start_enabled_components()
    return app.exec()
