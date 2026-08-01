from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from zapret_hub.services.components import ProcessManager, _TG_WS_PROXY_REQUIRED_FILES


class FakeLogging:
    def log(self, *_args, **_kwargs) -> None:
        return None

    def source_log_path(self, source: str) -> str:
        return source


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process ownership test")
def test_linux_pidfile_only_accepts_tg_worker(tmp_path: Path) -> None:
    manager = ProcessManager.__new__(ProcessManager)
    manager.storage = SimpleNamespace(paths=SimpleNamespace(runtime_dir=tmp_path / "runtime"))

    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "--worker", "tg-ws-proxy"]
    )
    try:
        manager._write_tg_proxy_pid(process.pid)
        assert manager._read_tg_proxy_pid() == process.pid

        manager._tg_proxy_pidfile().write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert manager._read_tg_proxy_pid() is None
        assert not manager._tg_proxy_pidfile().exists()
    finally:
        process.terminate()
        process.wait(timeout=5)
@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux process ownership test")
def test_linux_stop_terminates_managed_orphan(tmp_path: Path) -> None:
    manager = ProcessManager.__new__(ProcessManager)
    manager.storage = SimpleNamespace(paths=SimpleNamespace(runtime_dir=tmp_path / "runtime"))
    manager.logging = FakeLogging()
    manager.settings = SimpleNamespace(
        get=lambda: SimpleNamespace(tg_proxy_host="127.0.0.1", tg_proxy_port=19443)
    )
    manager._processes = {}
    manager._states = {}
    manager._log_streams = {}
    manager._port_listening_cache = {}
    manager._state_cache = []
    manager._state_cache_at = 0.0
    manager._creationflags = 0
    manager._startupinfo = None

    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)", "--worker", "tg-ws-proxy"]
    )
    original_pid_running = manager._pid_running
    manager._pid_running = lambda pid: process.poll() is None if pid == process.pid else original_pid_running(pid)
    try:
        manager._write_tg_proxy_pid(process.pid)
        state = manager._stop_component_unlocked("tg-ws-proxy")

        assert state.status == "stopped"
        assert process.poll() is not None
        assert not manager._tg_proxy_pidfile().exists()
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux source-only updater test")
def test_linux_updater_accepts_complete_source_archive_without_windows_exe(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive" / "tg-ws-proxy-v1.9.2"
    for relative in _TG_WS_PROXY_REQUIRED_FILES:
        target = archive_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            '__version__ = "1.9.1"\n' if relative == "proxy/__init__.py" else "# runtime module\n",
            encoding="utf-8",
        )
    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as archive:
        for path in archive_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(archive_root.parent))

    runtime_dir = tmp_path / "runtime"

    class Storage:
        paths = SimpleNamespace(runtime_dir=runtime_dir)

        @staticmethod
        def _detect_tgws_version() -> str:
            return "1.9.1"

        @staticmethod
        def create_backup(*_args):
            return None

        @staticmethod
        def ensure_layout() -> None:
            return None

    manager = ProcessManager.__new__(ProcessManager)
    manager.storage = Storage()
    manager.logging = FakeLogging()
    manager.list_states = lambda: []
    manager._download_to_file = lambda _url, destination, timeout=60: shutil.copy2(
        source_zip, destination
    )

    result = manager._install_tg_ws_proxy_release(
        {
            "latest_version": "1.9.2",
            "source_url": "https://example.invalid/tg-ws-proxy.zip",
            "exe_url": "",
        }
    )

    installed = runtime_dir / "tg-ws-proxy" / "proxy" / "__init__.py"
    assert result == {"status": "updated", "version": "1.9.2"}
    assert '__version__ = "1.9.2"' in installed.read_text(encoding="utf-8")
    assert not (runtime_dir / "tg-ws-proxy" / "docs").exists()
    assert not (runtime_dir / "tg-ws-proxy" / "windows.py").exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux source-only updater test")
def test_linux_updater_rejects_incomplete_source_archive(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive" / "tg-ws-proxy-v1.9.2"
    (archive_root / "proxy").mkdir(parents=True)
    (archive_root / "proxy" / "__init__.py").write_text('__version__ = "1.9.2"\n', encoding="utf-8")
    source_zip = tmp_path / "source.zip"
    with zipfile.ZipFile(source_zip, "w") as archive:
        for path in archive_root.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(archive_root.parent))

    runtime_dir = tmp_path / "runtime"

    class Storage:
        paths = SimpleNamespace(runtime_dir=runtime_dir)

        @staticmethod
        def _detect_tgws_version() -> str:
            return "1.9.1"

    manager = ProcessManager.__new__(ProcessManager)
    manager.storage = Storage()
    manager.list_states = lambda: []
    manager._download_to_file = lambda _url, destination, timeout=60: shutil.copy2(source_zip, destination)

    result = manager._install_tg_ws_proxy_release(
        {"latest_version": "1.9.2", "source_url": "https://example.invalid/tg-ws-proxy.zip", "exe_url": ""}
    )

    assert result["status"] == "error"
    assert "Incomplete tg-ws-proxy source archive" in result["error"]
    assert not runtime_dir.exists()
