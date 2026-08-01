from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace

from zapret_hub.services.components import ProcessManager
from zapret_hub.services.linux_zapret2 import LinuxZapret2Service, LinuxZapretService
from zapret_hub.services.storage import StorageManager


class FakeRunner:
    def __init__(self, states: list[tuple[int, str, str]]) -> None:
        self.states = list(states)
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        returncode, stdout, stderr = self.states.pop(0)
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)


def _which(name: str) -> str | None:
    paths = {
        "systemctl": "/usr/bin/systemctl",
        "pkexec": "/usr/bin/pkexec",
        "pgrep": "/usr/bin/pgrep",
        "nft": "/usr/sbin/nft",
    }
    return paths.get(name)


def test_status_reads_systemd_active_state() -> None:
    runner = FakeRunner([(0, "active\n", "")])
    service = LinuxZapret2Service(runner=runner, which=_which, geteuid=lambda: 1000, platform_name="linux")

    result = service.status()

    assert result.status == "running"
    assert runner.commands == [["/usr/bin/systemctl", "is-active", "zapret2.service"]]


def test_non_root_start_uses_pkexec_and_verifies_state() -> None:
    runner = FakeRunner([(0, "", ""), (0, "active\n", "")])
    service = LinuxZapret2Service(runner=runner, which=_which, geteuid=lambda: 1000, platform_name="linux")

    result = service.start()

    assert result.status == "running"
    assert runner.commands[0] == ["/usr/bin/pkexec", "/usr/bin/systemctl", "start", "zapret2.service"]


def test_dry_run_never_executes_command() -> None:
    runner = FakeRunner([])
    service = LinuxZapret2Service(runner=runner, which=_which, geteuid=lambda: 0, platform_name="linux")

    result = service.stop(dry_run=True)

    assert result.status == "planned"
    assert result.command == ("/usr/bin/systemctl", "stop", "zapret2.service")
    assert runner.commands == []


def test_diagnose_discovers_linux_binary(tmp_path: Path) -> None:
    binary = tmp_path / "binaries" / "linux-x86_64" / "nfqws2"
    binary.parent.mkdir(parents=True)
    binary.write_text("binary", encoding="utf-8")
    runner = FakeRunner([(3, "inactive\n", ""), (1, "", "")])
    service = LinuxZapret2Service(
        root_candidates=(tmp_path,),
        runner=runner,
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    report = service.diagnose()

    assert report["supported"] is True
    assert report["zapret2_root"] == str(tmp_path)
    assert report["nfqws2"] == str(binary)
    assert report["ready"] is True


def test_other_platform_is_reported_as_unsupported() -> None:
    service = LinuxZapret2Service(which=_which, geteuid=lambda: 1000, platform_name="win32")

    assert service.status().status == "unsupported"


def test_classic_zapret_status_uses_existing_systemd_unit() -> None:
    runner = FakeRunner([(0, "active\n", "")])
    service = LinuxZapretService(
        runner=runner,
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    result = service.status()

    assert result.status == "running"
    assert runner.commands == [
        ["/usr/bin/systemctl", "is-active", "zapret_discord_youtube.service"]
    ]


def test_classic_zapret_diagnose_discovers_nfqws(tmp_path: Path) -> None:
    binary = tmp_path / "nfqws"
    binary.write_text("binary", encoding="utf-8")
    runner = FakeRunner([(0, "active\n", "")])
    service = LinuxZapretService(
        root_candidates=(tmp_path,),
        runner=runner,
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    report = service.diagnose()

    assert report["zapret_root"] == str(tmp_path)
    assert report["nfqws"] == str(binary)
    assert report["service_state"] == "running"
    assert report["ready"] is True


def test_classic_zapret_dry_run_uses_pkexec() -> None:
    runner = FakeRunner([])
    service = LinuxZapretService(
        runner=runner,
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    result = service.stop(dry_run=True)

    assert result.status == "planned"
    assert result.command == (
        "/usr/bin/pkexec",
        "/usr/bin/systemctl",
        "stop",
        "zapret_discord_youtube.service",
    )
    assert runner.commands == []


def test_shutdown_keeps_external_linux_services_running() -> None:
    manager = ProcessManager.__new__(ProcessManager)
    manager._linux_zapret = object()
    manager._linux_zapret2 = object()
    manager.list_components = lambda: [
        SimpleNamespace(id="zapret"),
        SimpleNamespace(id="zapret2"),
        SimpleNamespace(id="tg-ws-proxy"),
    ]
    stopped: list[str] = []
    manager.stop_component = lambda component_id: stopped.append(component_id) or SimpleNamespace(
        component_id=component_id,
        status="stopped",
    )
    manager._cleanup_merged_runtime = lambda: None

    manager.stop_all(include_external_services=False)

    assert stopped == ["tg-ws-proxy"]


def test_storage_reads_version_from_installed_linux_zapret2(
    tmp_path: Path,
    monkeypatch,
) -> None:
    installed_root = tmp_path / "zapret2"
    installed_root.mkdir()
    (installed_root / ".zapret-hub-version").write_text("2026-07-31 (569297c)\n", encoding="utf-8")
    monkeypatch.setenv("ZAPRET_HUB_ZAPRET2_ROOT", str(installed_root))
    storage = StorageManager(SimpleNamespace(runtime_dir=tmp_path / "runtime"))

    assert storage._detect_zapret2_version() == "2026-07-31 (569297c)"
