from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_INSTALLER = PROJECT_ROOT / "install.sh"
USER_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux.sh"
SYSTEM_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux_system.sh"
HAPP_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux_happ.sh"


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
    assert "python3-venv" in output
    assert "nodejs npm" in output
    assert "polkitd pkexec nftables" in output
    assert "policykit-1" not in output
    assert "curl git tar gzip" in output
    apt_line = next(line for line in output.splitlines() if "apt-get install" in line)
    assert "telegram-desktop" not in apt_line
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
    apt_line = next(line for line in result.stdout.splitlines() if "apt-get install" in line)
    assert "telegram-desktop" in apt_line


def test_system_installer_never_changes_live_network_service_state() -> None:
    script = SYSTEM_INSTALLER.read_text(encoding="utf-8")
    classic_helper = (
        PROJECT_ROOT / "scripts" / "install_linux_classic_zapret.sh"
    ).read_text(encoding="utf-8")
    happ_helper = HAPP_INSTALLER.read_text(encoding="utf-8")

    assert re.search(r"^systemctl daemon-reload$", script, re.MULTILINE)
    assert not re.search(r"^systemctl (?:enable|disable)", script, re.MULTILINE)
    assert not re.search(r"^systemctl (?:start|stop|restart)", script, re.MULTILINE)
    assert not re.search(
        r"^systemctl (?:enable|disable|start|stop|restart)", classic_helper, re.MULTILINE
    )
    assert not re.search(r"\b(?:nmcli|wg-quick|openvpn)\b", script)
    assert not re.search(r"\b(?:nmcli|wg-quick|openvpn)\b", classic_helper)
    assert not re.search(
        r"^systemctl (?:enable|disable|stop|restart)", happ_helper, re.MULTILINE
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
        PROJECT_ROOT / "packaging" / "linux" / "zapret_discord_youtube.service.in",
        PROJECT_ROOT / "packaging" / "polkit" / "49-zapret-hub.rules",
        PROJECT_ROOT / "packaging" / "linux" / "zapret-hosts-user.txt",
        PROJECT_ROOT / "web_ui" / "package-lock.json",
        PROJECT_ROOT / "ui_assets" / "icons" / "app.png",
    )

    assert all(path.is_file() for path in required)
    assert os.access(USER_INSTALLER, os.X_OK)
    assert os.access(ROOT_INSTALLER, os.X_OK)
    assert os.access(SYSTEM_INSTALLER, os.X_OK)
    assert os.access(HAPP_INSTALLER, os.X_OK)


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
    assert "sha256sum -c -" in helper
    assert "preserving it without restart or upgrade" in helper
