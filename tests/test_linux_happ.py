from __future__ import annotations

from pathlib import Path
import subprocess

from zapret_hub.services.linux_happ import LinuxHappService


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
