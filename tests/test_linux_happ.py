from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace

from zapret_hub.services.backend_worker import _sync_bypass_enabled_for_mode
from zapret_hub.services.components import ProcessManager
from zapret_hub.services.linux_happ import LinuxHappService
from zapret_hub.services.linux_happ import LinuxHappResult


class _PopenRecorder:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def __call__(self, command, **_kwargs):
        self.commands.append(list(command))
        return object()


def _executable(tmp_path: Path) -> Path:
    path = tmp_path / "happ"
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_status_uses_official_core_process(tmp_path: Path) -> None:
    executable = _executable(tmp_path)
    service = LinuxHappService(
        executable_candidates=(executable,),
        connected_pid=lambda: 4242,
        which=lambda _name: None,
    )

    result = service.status()

    assert result.status == "running"
    assert result.pid == 4242


def test_start_uses_connect_deeplink_without_restarting_daemon(tmp_path: Path) -> None:
    executable = _executable(tmp_path)
    popen = _PopenRecorder()
    pids = iter((None, 4242))
    commands: list[list[str]] = []

    def runner(command, **_kwargs):
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "active\n", "")

    service = LinuxHappService(
        executable_candidates=(executable,),
        connected_pid=lambda: next(pids),
        popen=popen,
        runner=runner,
        which=lambda name: "/usr/bin/systemctl" if name == "systemctl" else None,
        sleep=lambda _seconds: None,
    )

    result = service.start()

    assert result.status == "running"
    assert popen.commands == [[str(executable.resolve()), "happ://connect"]]
    assert commands == [["/usr/bin/systemctl", "is-active", "happd.service"]]
    assert not any("restart" in command or "stop" in command for command in commands)


def test_stop_uses_disconnect_deeplink_and_never_stops_daemon(tmp_path: Path) -> None:
    executable = _executable(tmp_path)
    popen = _PopenRecorder()
    pids = iter((4242, None))
    service = LinuxHappService(
        executable_candidates=(executable,),
        connected_pid=lambda: next(pids),
        popen=popen,
        which=lambda _name: None,
        sleep=lambda _seconds: None,
    )

    result = service.stop()

    assert result.status == "stopped"
    assert popen.commands == [[str(executable.resolve()), "happ://disconnect"]]


def test_open_uses_official_open_deeplink(tmp_path: Path) -> None:
    executable = _executable(tmp_path)
    popen = _PopenRecorder()
    service = LinuxHappService(
        executable_candidates=(executable,),
        popen=popen,
        which=lambda _name: None,
    )

    result = service.open()

    assert result.status == "opened"
    assert popen.commands == [[str(executable.resolve()), "happ://open"]]


def test_linux_happ_start_does_not_stop_zapret_services() -> None:
    manager = ProcessManager.__new__(ProcessManager)
    manager._linux_happ = SimpleNamespace(
        start=lambda: LinuxHappResult("running", pid=4242, command=("happ", "happ://connect"))
    )
    manager._linux_zapret = SimpleNamespace(status=lambda: (_ for _ in ()).throw(AssertionError("Zapret was inspected")))
    manager._linux_zapret2 = SimpleNamespace(status=lambda: (_ for _ in ()).throw(AssertionError("Zapret2 was inspected")))
    manager._states = {}
    manager.logging = SimpleNamespace(log=lambda *_args, **_kwargs: None)

    state = manager._start_goshkow_vpn("goshkow-vpn")

    assert state.status == "running"
    assert state.pid == 4242


def test_linux_runtime_selection_preserves_enabled_happ() -> None:
    values = SimpleNamespace(
        enabled_component_ids=["zapret", "goshkow-vpn"],
        autostart_component_ids=["goshkow-vpn"],
    )

    class Settings:
        def get(self):
            return values

        def update(self, **changes):
            for key, value in changes.items():
                setattr(values, key, value)
            return values

    context = SimpleNamespace(
        settings=Settings(),
        processes=SimpleNamespace(_linux_happ=SimpleNamespace(available=True)),
    )

    _sync_bypass_enabled_for_mode(context, "zapret2")

    assert values.selected_runtime_mode == "zapret2"
    assert set(values.enabled_component_ids) == {"zapret2", "goshkow-vpn"}
    assert values.autostart_component_ids == ["goshkow-vpn"]


def test_linux_runtime_cleanup_never_disconnects_happ() -> None:
    manager = ProcessManager.__new__(ProcessManager)
    manager._linux_zapret2 = object()
    manager._linux_happ = SimpleNamespace(
        status=lambda: (_ for _ in ()).throw(AssertionError("Happ status was inspected"))
    )

    manager.stop_running_bypass_copies("goshkow-vpn")
