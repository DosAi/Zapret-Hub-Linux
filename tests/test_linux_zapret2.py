from __future__ import annotations

from pathlib import Path
import os
import subprocess
from types import SimpleNamespace

import zapret_hub.services.linux_zapret2 as lz
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


def test_classic_zapret_discovery_skips_incomplete_foreign_root(tmp_path: Path) -> None:
    incomplete = tmp_path / "foreign"
    fallback = tmp_path / "managed"
    incomplete.mkdir()
    fallback.mkdir()
    binary = fallback / "nfqws"
    binary.write_text("binary", encoding="utf-8")
    service = LinuxZapretService(
        root_candidates=(incomplete, fallback),
        runner=FakeRunner([]),
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    assert service.discover_root() == fallback
    assert service.find_nfqws() == binary


def test_classic_zapret_discovery_skips_unreadable_foreign_root(
    tmp_path: Path, monkeypatch
) -> None:
    unreadable = tmp_path / "foreign"
    fallback = tmp_path / "managed"
    unreadable.mkdir()
    fallback.mkdir()
    binary = fallback / "nfqws"
    binary.write_text("binary", encoding="utf-8")
    real_access = os.access

    def fake_access(path, mode, **kwargs):
        if str(path) == str(unreadable) and mode == os.R_OK:
            return False
        return real_access(path, mode, **kwargs)

    monkeypatch.setattr(lz.os, "access", fake_access)
    service = LinuxZapretService(
        root_candidates=(unreadable, fallback),
        runner=FakeRunner([]),
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    assert service.discover_root() == fallback


def test_classic_zapret_default_roots_include_apps_install(monkeypatch) -> None:
    monkeypatch.delenv("ZAPRET_HUB_ZAPRET_ROOT", raising=False)
    monkeypatch.setenv("HOME", "/home/tester")

    roots = LinuxZapretService._default_roots()

    assert Path("/home/tester/Apps/zapret-discord-youtube-linux") in roots
    assert Path("/opt/zapret-discord-youtube-linux") in roots


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
    manager._linux_happ = object()
    manager.list_components = lambda: [
        SimpleNamespace(id="zapret"),
        SimpleNamespace(id="zapret2"),
        SimpleNamespace(id="goshkow-vpn"),
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


def _classic_root(tmp_path: Path) -> Path:
    root = tmp_path / "classic"
    repo = root / "zapret-latest"
    custom = root / "custom-strategies"
    repo.mkdir(parents=True)
    custom.mkdir(parents=True)
    (root / "nfqws").write_text("binary", encoding="utf-8")
    (repo / "general.bat").write_text("", encoding="utf-8")
    (repo / "general_alt2.bat").write_text("", encoding="utf-8")
    (repo / "service.bat").write_text("", encoding="utf-8")
    (custom / "minecraft.bat").write_text("", encoding="utf-8")
    (root / "conf.env").write_text(
        "interface=any\ngamefiltertcp=false\nstrategy=general_alt2.bat\nfirewall_backend=auto\n",
        encoding="utf-8",
    )
    return root


def _classic_service(tmp_path: Path, runner=None) -> LinuxZapretService:
    return LinuxZapretService(
        root_candidates=(_classic_root(tmp_path),),
        runner=runner or FakeRunner([]),
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )


def _present_unit(tmp_path: Path) -> Path:
    unit_file = tmp_path / "unit" / "zapret_discord_youtube.service"
    unit_file.parent.mkdir(parents=True)
    unit_file.write_text("[Unit]\n", encoding="utf-8")
    return unit_file


def test_classic_zapret_lists_strategies_in_upstream_order(tmp_path: Path) -> None:
    service = _classic_service(tmp_path)

    assert service.list_strategies() == ["minecraft.bat", "general.bat", "general_alt2.bat"]


def test_classic_zapret_strategy_path_prefers_custom_copy(tmp_path: Path) -> None:
    service = _classic_service(tmp_path)
    root = service.discover_root()

    assert service.strategy_path("general_alt2.bat") == (root / "zapret-latest" / "general_alt2.bat").resolve()
    assert service.strategy_path("minecraft.bat") == (root / "custom-strategies" / "minecraft.bat").resolve()


def test_classic_zapret_reads_current_strategy_from_conf_env(tmp_path: Path) -> None:
    service = _classic_service(tmp_path)

    assert service.current_strategy() == "general_alt2.bat"


def test_classic_zapret_apply_strategy_rewrites_only_strategy_line(tmp_path: Path) -> None:
    service = _classic_service(tmp_path)

    result = service.apply_strategy("minecraft.bat")

    assert result.status == "ok"
    root = service.discover_root()
    assert (root / "conf.env").read_text(encoding="utf-8") == (
        "interface=any\ngamefiltertcp=false\nstrategy=minecraft.bat\nfirewall_backend=auto\n"
    )
    assert service.current_strategy() == "minecraft.bat"


def test_classic_zapret_apply_strategy_appends_when_missing(tmp_path: Path) -> None:
    root = tmp_path / "classic"
    repo = root / "zapret-latest"
    repo.mkdir(parents=True)
    (root / "nfqws").write_text("binary", encoding="utf-8")
    (repo / "general.bat").write_text("", encoding="utf-8")
    (root / "conf.env").write_text("interface=any\n", encoding="utf-8")
    service = LinuxZapretService(
        root_candidates=(root,),
        runner=FakeRunner([]),
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    result = service.apply_strategy("general.bat")

    assert result.status == "ok"
    assert (root / "conf.env").read_text(encoding="utf-8") == "interface=any\nstrategy=general.bat\n"


def test_classic_zapret_apply_strategy_rejects_unknown_and_unsafe_names(tmp_path: Path) -> None:
    service = _classic_service(tmp_path)

    assert service.apply_strategy("missing.bat").status == "error"
    assert service.apply_strategy("../../etc/passwd").status == "error"
    assert service.apply_strategy("general.bat; rm -rf /").status == "error"


def test_classic_zapret_apply_strategy_is_noop_when_already_active(tmp_path: Path) -> None:
    service = _classic_service(tmp_path)

    result = service.apply_strategy("general_alt2.bat")

    assert result.status == "ok"
    root = service.discover_root()
    assert (root / "conf.env").read_text(encoding="utf-8") == (
        "interface=any\ngamefiltertcp=false\nstrategy=general_alt2.bat\nfirewall_backend=auto\n"
    )


def test_classic_zapret_apply_strategy_elevates_via_helper_for_root_owned_file(
    tmp_path: Path, monkeypatch
) -> None:
    helper = tmp_path / "zapret-hub-set-strategy"
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("ZAPRET_HUB_ZAPRET_STRATEGY_HELPER", str(helper))
    real_access = os.access

    def _deny_write_only(path, mode, **kwargs):
        if mode == os.W_OK:
            return False
        return real_access(path, mode, **kwargs)

    monkeypatch.setattr("zapret_hub.services.linux_zapret2.os.access", _deny_write_only)
    runner = FakeRunner([(0, "", "")])
    service = _classic_service(tmp_path, runner=runner)

    result = service.apply_strategy("minecraft.bat")

    assert result.status == "ok"
    assert runner.commands == [
        ["/usr/bin/pkexec", str(helper), str(service.discover_root() / "conf.env"), "minecraft.bat"]
    ]


def test_classic_zapret_restart_maps_to_running(tmp_path: Path, monkeypatch) -> None:
    unit_file = _present_unit(tmp_path)
    monkeypatch.setattr(LinuxZapretService, "_systemd_unit_paths", lambda self: (unit_file,))
    runner = FakeRunner([(0, "", ""), (0, "active\n", "")])
    service = _classic_service(tmp_path, runner=runner)

    result = service.restart()

    assert result.status == "running"
    assert runner.commands[0] == [
        "/usr/bin/pkexec",
        "/usr/bin/systemctl",
        "restart",
        "zapret_discord_youtube.service",
    ]


def test_process_manager_lists_linux_zapret_generals(tmp_path: Path) -> None:
    manager = ProcessManager.__new__(ProcessManager)
    manager._linux_zapret = _classic_service(tmp_path)
    manager._linux_zapret2 = object()
    manager.settings = SimpleNamespace(selected_service_ids=[])
    manager._general_option_sort_key = ProcessManager._general_option_sort_key.__get__(manager)

    options = manager.list_zapret_generals()

    assert [item["id"] for item in options] == [
        "classic|general_alt2.bat",
        "classic|general.bat",
        "classic|minecraft.bat",
    ]
    assert all(item["bundle_id"] == "classic" for item in options)


def test_process_manager_current_zapret_general_matches_conf_env(tmp_path: Path) -> None:
    manager = ProcessManager.__new__(ProcessManager)
    manager._linux_zapret = _classic_service(tmp_path)
    manager._linux_zapret2 = object()
    manager._general_option_sort_key = ProcessManager._general_option_sort_key.__get__(manager)

    assert manager.current_zapret_general() == "classic|general_alt2.bat"


def test_process_manager_apply_zapret_general_writes_conf_env(tmp_path: Path) -> None:
    manager = ProcessManager.__new__(ProcessManager)
    service = _classic_service(tmp_path)
    manager._linux_zapret = service
    manager._linux_zapret2 = object()
    manager.settings = SimpleNamespace(selected_service_ids=[])
    manager._general_option_sort_key = ProcessManager._general_option_sort_key.__get__(manager)
    manager.logging = SimpleNamespace(log=lambda *_, **__: None)

    assert manager.apply_zapret_general("classic|minecraft.bat") is True
    assert service.current_strategy() == "minecraft.bat"
    assert manager.apply_zapret_general("classic|missing.bat") is False


def test_process_manager_linux_general_diagnostics_keeps_current_when_stopped(tmp_path: Path) -> None:
    runner = FakeRunner([(3, "inactive\n", "")])
    manager = ProcessManager.__new__(ProcessManager)
    manager._linux_zapret = _classic_service(tmp_path, runner=runner)
    manager._linux_zapret2 = object()
    manager.settings = SimpleNamespace(get=lambda: SimpleNamespace(selected_service_ids=[]))
    manager.storage = SimpleNamespace(paths=SimpleNamespace(runtime_dir=tmp_path / "runtime"))
    manager._general_option_sort_key = ProcessManager._general_option_sort_key.__get__(manager)

    results = manager.run_general_diagnostics()

    assert results == [
        {
            "id": "classic|general_alt2.bat",
            "name": "general_alt2.bat",
            "bundle": "Classic Zapret",
            "status": "ok",
            "error": "service is not running; kept the conf.env strategy",
            "passed_targets": "0",
            "total_targets": "0",
            "failed_targets": [],
            "ipset_mode": "loaded",
            "game_mode": "tcpudp",
        }
    ]
    assert service_current_strategy(manager) == "general_alt2.bat"


def test_process_manager_linux_general_diagnostics_live_test_keeps_winner(
    tmp_path: Path, monkeypatch
) -> None:
    root = _classic_root(tmp_path)
    unit_file = _present_unit(tmp_path)
    monkeypatch.setattr(LinuxZapretService, "_systemd_unit_paths", lambda self: (unit_file,))
    runner = FakeRunner(
        [
            (0, "active\n", ""),  # initial status
            (0, "", ""),  # restart minecraft.bat
            (0, "active\n", ""),  # status after restart
            (0, "active\n", ""),  # final status in finally
        ]
    )
    manager = ProcessManager.__new__(ProcessManager)
    manager._linux_zapret = LinuxZapretService(
        root_candidates=(root,),
        runner=runner,
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )
    manager._linux_zapret2 = object()
    manager.settings = SimpleNamespace(get=lambda: SimpleNamespace(selected_service_ids=[]))
    manager.storage = SimpleNamespace(paths=SimpleNamespace(runtime_dir=tmp_path / "runtime"))
    manager._general_option_sort_key = ProcessManager._general_option_sort_key.__get__(manager)
    manager._target_is_reachable = lambda target: True
    manager._run_quiet = lambda *_, **__: subprocess.CompletedProcess([], 0, "200", "")

    results = manager.run_general_diagnostics()

    assert results and results[0]["status"] == "ok"
    assert results[0]["passed_targets"] == "1"
    assert "strategy=" in (root / "conf.env").read_text(encoding="utf-8")
    assert len(results) == 1


def service_current_strategy(manager: ProcessManager) -> str:
    return str(manager._linux_zapret.current_strategy())


def _which_with_unit_helper(name: str) -> str | None:
    paths = {
        "systemctl": "/usr/bin/systemctl",
        "pkexec": "/usr/bin/pkexec",
        "pgrep": "/usr/bin/pgrep",
        "nft": "/usr/sbin/nft",
        "zapret-hub-install-classic-unit": "/usr/local/sbin/zapret-hub-install-classic-unit",
    }
    return paths.get(name)


def test_classic_zapret_start_installs_missing_unit(tmp_path: Path, monkeypatch) -> None:
    root = _classic_root(tmp_path)
    unit_file = tmp_path / "unit" / "zapret_discord_youtube.service"
    unit_file.parent.mkdir(parents=True)
    monkeypatch.setattr(LinuxZapretService, "_systemd_unit_paths", lambda self: (unit_file,))
    runner = FakeRunner(
        [
            (0, "", ""),  # helper install
            (0, "", ""),  # systemctl start
            (0, "active\n", ""),  # status verification
        ]
    )
    service = LinuxZapretService(
        root_candidates=(root,),
        runner=runner,
        which=_which_with_unit_helper,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    result = service.start()

    assert result.status == "running"
    assert runner.commands == [
        ["/usr/bin/pkexec", "/usr/local/sbin/zapret-hub-install-classic-unit", str(root)],
        ["/usr/bin/pkexec", "/usr/bin/systemctl", "start", "zapret_discord_youtube.service"],
        ["/usr/bin/systemctl", "is-active", "zapret_discord_youtube.service"],
    ]


def test_classic_zapret_start_skips_install_when_unit_exists(
    tmp_path: Path, monkeypatch
) -> None:
    root = _classic_root(tmp_path)
    unit_file = tmp_path / "unit" / "zapret_discord_youtube.service"
    unit_file.parent.mkdir(parents=True)
    unit_file.write_text("[Unit]\n", encoding="utf-8")
    monkeypatch.setattr(LinuxZapretService, "_systemd_unit_paths", lambda self: (unit_file,))
    runner = FakeRunner([(0, "", ""), (0, "active\n", "")])
    service = LinuxZapretService(
        root_candidates=(root,),
        runner=runner,
        which=_which_with_unit_helper,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    result = service.start()

    assert result.status == "running"
    assert runner.commands == [
        ["/usr/bin/pkexec", "/usr/bin/systemctl", "start", "zapret_discord_youtube.service"],
        ["/usr/bin/systemctl", "is-active", "zapret_discord_youtube.service"],
    ]


def test_classic_zapret_start_reports_missing_unit_helper(tmp_path: Path) -> None:
    root = _classic_root(tmp_path)
    runner = FakeRunner([])
    service = LinuxZapretService(
        root_candidates=(root,),
        runner=runner,
        which=_which,
        geteuid=lambda: 1000,
        platform_name="linux",
    )

    result = service.start()

    assert result.status == "error"
    assert "zapret-hub-install-classic-unit" in result.message
    assert runner.commands == []
