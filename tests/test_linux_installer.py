from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess


PROJECT_ROOT = Path(__file__).resolve().parents[1]
USER_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux.sh"
SYSTEM_INSTALLER = PROJECT_ROOT / "scripts" / "install_linux_system.sh"


def test_linux_installer_dry_run_is_complete_and_non_mutating() -> None:
    result = subprocess.run(
        [str(USER_INSTALLER), "--dry-run", "--no-launch"],
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
    assert "policykit-1 nftables" in output
    apt_line = next(line for line in output.splitlines() if "apt-get install" in line)
    assert "telegram-desktop" not in apt_line
    assert "install bundled Zapret2" in output
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

    assert re.search(r"^systemctl daemon-reload$", script, re.MULTILINE)
    assert re.search(r"^systemctl enable zapret2\.service$", script, re.MULTILINE)
    assert not re.search(r"^systemctl (?:start|stop|restart)", script, re.MULTILINE)
    assert not re.search(r"\b(?:nmcli|wg-quick|openvpn)\b", script)


def test_clean_checkout_contains_all_installer_payloads() -> None:
    required = (
        PROJECT_ROOT / "runtime" / "zapret2" / "config.default",
        PROJECT_ROOT / "runtime" / "zapret2" / "install_bin.sh",
        PROJECT_ROOT / "runtime" / "zapret2" / "init.d" / "systemd" / "zapret2.service",
        PROJECT_ROOT / "runtime" / "zapret2" / "binaries" / "linux-x86_64" / "nfqws2",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "tg_ws_proxy.py",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "balancer.py",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "raw_websocket.py",
        PROJECT_ROOT / "runtime" / "tg-ws-proxy" / "proxy" / "stats.py",
        PROJECT_ROOT / "packaging" / "polkit" / "49-zapret-hub.rules",
        PROJECT_ROOT / "packaging" / "linux" / "zapret-hosts-user.txt",
        PROJECT_ROOT / "web_ui" / "package-lock.json",
        PROJECT_ROOT / "ui_assets" / "icons" / "app.png",
    )

    assert all(path.is_file() for path in required)
    assert os.access(USER_INSTALLER, os.X_OK)
    assert os.access(SYSTEM_INSTALLER, os.X_OK)
