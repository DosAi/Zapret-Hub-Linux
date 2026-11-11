from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_INSTALLER = PROJECT_ROOT / "install.sh"
USER_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux.sh"
SYSTEM_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux_system.sh"
ZAPRET2_UPDATE_HELPER = PROJECT_ROOT / "scripts" / "update_linux_zapret2_system.sh"
HAPP_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux_happ.sh"
DISTRO_LIB = PROJECT_ROOT / "scripts" / "lib" / "distro.sh"
ROOT_UNINSTALLER = PROJECT_ROOT / "uninstall.sh"
USER_UNINSTALLER = PROJECT_ROOT / "scripts" / "uninstall_linux.sh"
SYSTEM_UNINSTALLER = PROJECT_ROOT / "scripts" / "uninstall_linux_system.sh"


def _sh(source: str) -> str:
    result = subprocess.run(
        ["sh", "-c", f". scripts/lib/distro.sh; {source}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    return result.stdout.strip()


def _detected_deps() -> list[str]:
    return _sh("zh_deps").split()


def test_linux_installer_dry_run_is_complete_and_non_mutating() -> None:
    result = subprocess.run(
        [str(ROOT_INSTALLER), "--dry-run", "--no-launch"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    for dep in _detected_deps():
        assert dep in output, f"missing package {dep!r} in dry-run output"
    assert "policykit-1" not in output
    assert "curl git tar gzip" in output
    install_line = next(line for line in output.splitlines() if " install -y " in line)
    assert "telegram-desktop" not in install_line
    assert "install classic Zapret for Linux release 0.5.0" in output
    assert "verify classic Zapret source archive SHA-256" in output
    assert "install bundled Zapret2" in output
    assert "verify bundled TG WS Proxy" in output
    assert "install official Happ 3.3.6" in output
    assert "preserve an existing Happ installation and active tunnel" in output
    assert "without starting or restarting" in output
    assert "npm ci && npm run build" in output


def test_linux_installer_can_install_telegram_explicitly() -> None:
    result = subprocess.run(
        [str(USER_INSTALLER), "--dry-run", "--no-launch", "--with-telegram"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "telegram-desktop" in result.stdout


def test_linux_installer_rejects_alpine_instead_of_partial_install(tmp_path: Path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=alpine\nPRETTY_NAME="Alpine test"\n', encoding="utf-8")
    result = subprocess.run(
        [str(USER_INSTALLER), "--dry-run", "--no-launch"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
        env={**os.environ, "ZH_OS_RELEASE": str(os_release)},
    )

    assert result.returncode != 0
    assert "Alpine/OpenRC is not supported yet" in result.stderr


def test_system_installer_never_changes_live_network_service_state() -> None:
    script = SYSTEM_INSTALLER.read_text(encoding="utf-8")
    classic_helper = (
        PROJECT_ROOT / "scripts" / "install_linux_classic_zapret.sh"
    ).read_text(encoding="utf-8")
    happ_helper = HAPP_INSTALLER.read_text(encoding="utf-8")

    assert re.search(r"^\s*systemctl daemon-reload$", script, re.MULTILINE)
    assert not re.search(r"^\s*systemctl (?:enable|disable)", script, re.MULTILINE)
    assert not re.search(r"^\s*systemctl (?:start|stop|restart)", script, re.MULTILINE)
    assert not re.search(
        r"^\s*systemctl (?:enable|disable|start|stop|restart)", classic_helper, re.MULTILINE
    )
    assert not re.search(r"\b(?:nmcli|wg-quick|openvpn)\b", script)
    assert not re.search(r"\b(?:nmcli|wg-quick|openvpn)\b", classic_helper)
    assert not re.search(
        r"^\s*systemctl (?:enable|disable|stop|restart)", happ_helper, re.MULTILINE
    )
    assert not re.search(r"\b(?:nmcli|wg-quick|openvpn)\b", happ_helper)


def test_clean_checkout_contains_all_installer_payloads() -> None:
    required = (
        PROJECT_ROOT / "runtime" / "zapret2" / "config.default",
        PROJECT_ROOT / "runtime" / "zapret2" / "install_bin.sh",
        PROJECT_ROOT / "runtime" / "zapret2" / "init.d" / "systemd" / "zapret2.service",
        PROJECT_ROOT / "runtime" / "zapret2" / "binaries" / "linux-x86_64" / "nfqws2",
        PROJECT_ROOT / "runtime" / "zapret2" / "binaries" / "linux-arm64" / "nfqws2",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "tg_ws_proxy.py",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "balancer.py",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "raw_websocket.py",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "stats.py",
        PROJECT_ROOT / "scripts" / "install_linux_classic_zapret.sh",
        HAPP_INSTALLER,
        DISTRO_LIB,
        PROJECT_ROOT / "packaging" / "linux" / "zapret_discord_youtube.service.in",
        PROJECT_ROOT / "packaging" / "polkit" / "49-zapret-hub.rules",
        PROJECT_ROOT / "packaging" / "linux" / "zapret-hosts-user.txt",
        PROJECT_ROOT / "web_ui" / "package-lock.json",
        PROJECT_ROOT / "ui_assets" / "icons" / "app.png",
        ROOT_UNINSTALLER,
        USER_UNINSTALLER,
        SYSTEM_UNINSTALLER,
        ZAPRET2_UPDATE_HELPER,
        PROJECT_ROOT / "src" / "zapret_hub" / "uninstaller.py",
        PROJECT_ROOT / "web_ui" / "src" / "pages" / "UninstallPage.tsx",
    )

    assert all(path.is_file() for path in required)
    assert os.access(USER_INSTALLER, os.X_OK)
    assert os.access(ROOT_INSTALLER, os.X_OK)
    assert os.access(SYSTEM_INSTALLER, os.X_OK)
    assert os.access(HAPP_INSTALLER, os.X_OK)
    assert os.access(ROOT_UNINSTALLER, os.X_OK)
    assert os.access(USER_UNINSTALLER, os.X_OK)
    assert os.access(SYSTEM_UNINSTALLER, os.X_OK)
    assert os.access(ZAPRET2_UPDATE_HELPER, os.X_OK)


def test_linux_uninstaller_dry_run_is_safe_and_cross_distro() -> None:
    result = subprocess.run(
        [str(ROOT_UNINSTALLER), "--dry-run"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert ".zapret-hub-managed" in output
    assert "Preserving Happ" in output
    assert str(PROJECT_ROOT) in output


def test_linux_uninstaller_preserves_unmanaged_components_and_dependencies() -> None:
    user_script = USER_UNINSTALLER.read_text(encoding="utf-8")
    system_script = SYSTEM_UNINSTALLER.read_text(encoding="utf-8")

    assert "--cli" in user_script
    assert "zapret_hub.uninstaller" in user_script
    assert "--remove-happ" in user_script
    assert "--purge-data" in user_script
    assert ".zapret-hub-managed" in system_script
    assert "managed by Zapret Hub" in system_script
    assert "Preserving unmanaged" in system_script
    assert "zh_pkg_remove happ" in system_script
    assert "zh_deps" not in system_script
    installer = USER_INSTALLER.read_text(encoding="utf-8")
    assert "zapret-hub-uninstall.desktop" in installer
    assert "Name[ru]=Удалить Zapret Hub" in installer


def test_repository_contains_only_linux_runtime_payloads() -> None:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    tracked = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    forbidden_suffixes = {".exe", ".dll", ".sys", ".bat", ".ps1", ".ico"}
    forbidden_prefixes = {
        "assets/",
        "installer/",
        "installer_web/",
        "uninstaller_web/",
        "runtime/v2rayN/",
        "runtime/zapret-discord-youtube/",
        "sample_data/default_mods/",
    }

    assert not {path for path in tracked if Path(path).suffix.lower() in forbidden_suffixes}
    assert not {
        path
        for path in tracked
        if any(path.startswith(prefix) for prefix in forbidden_prefixes)
    }


def test_classic_zapret_source_is_pinned_and_verified() -> None:
    helper = (PROJECT_ROOT / "scripts" / "install_linux_classic_zapret.sh").read_text(
        encoding="utf-8"
    )

    assert "ADAPTER_REVISION=2136b8199474233f8018bc696fa97ef5d49320ff" in helper
    assert "ADAPTER_SHA256=105c9088da598936593ff6a52cbf4759ccea15cfe149c4254f9cdece919365a7" in helper
    assert 'sha256sum -c -' in helper
    assert "/master" not in helper


def test_happ_package_is_pinned_and_verified() -> None:
    helper = HAPP_INSTALLER.read_text(encoding="utf-8")

    assert "HAPP_VERSION=3.3.6" in helper
    assert "a7dac51277387bfe1049b1ad40f40f2e74af233a5eab020b5be1a622effc46a4" in helper
    assert "a4d3d6dcab1db61db23cdf0f86bce736014887262b570927befe48cb49f14aa6" in helper
    assert "bf7078723cd0761ea929edbc75fb6d10464920691f7cdcec47579254c3410d9b" in helper
    assert "300c762a2e6d08773b6f4432f207f7dcb42ade8c2565738a06b4c18dfa2b3b94" in helper
    assert "30eafd999ad5a99c7cb8ea780c4269f7fe6c4eedb1df50234e4fb44aa0c7d8a7" in helper
    assert "25c8ea919902d6ed6deabf82b49184bbf5626fff88e4956cf65e5327388f28eb" in helper
    assert "sha256sum -c -" in helper
    assert 'PACKAGE_SUFFIX=.deb' in helper
    assert 'PACKAGE_SUFFIX=.rpm' in helper
    assert 'PACKAGE_SUFFIX=.pkg.tar.zst' in helper
    assert "preserving it without restart or upgrade" in helper


def test_zapret2_system_updater_is_transactional_and_managed_only() -> None:
    helper = ZAPRET2_UPDATE_HELPER.read_text(encoding="utf-8")

    assert ".zapret-hub-managed" in helper
    assert "Refusing to update unmanaged" in helper
    assert "zapret-hub-stage" in helper
    assert "zapret-hub-backup" in helper
    assert "systemctl is-active" in helper
    assert "systemctl stop" in helper
    assert "systemctl start" in helper
    assert "previous installation was restored" in helper
    assert 'cp -a -- "$TARGET/config"' in helper


def test_network_probes_use_native_linux_arguments() -> None:
    components = (PROJECT_ROOT / "src" / "zapret_hub" / "services" / "components.py").read_text(
        encoding="utf-8"
    )

    assert 'output_sink = "NUL" if sys.platform.startswith("win") else "/dev/null"' in components
    assert '["ping", "-c", "1", "-W", "3", host]' in components
