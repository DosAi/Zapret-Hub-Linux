from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(source: str, os_release: str, extra_env: dict[str, str] | None = None) -> str:
    fd, path = tempfile.mkstemp(prefix="zh-os-release-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(os_release)
        env = {**os.environ, "ZH_OS_RELEASE": path}
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            ["sh", "-c", f". scripts/lib/distro.sh; {source}"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
            env=env,
        )
        return result.stdout.strip()
    finally:
        os.unlink(path)


def _family(os_release: str) -> str:
    return _run("zh_distro_family", os_release)


def _os_release(id_line: str, id_like: str = "") -> str:
    return f"ID={id_line}\nID_LIKE=\"{id_like}\"\n"


def test_family_detection_by_id() -> None:
    cases = {
        "debian": "debian",
        "ubuntu": "debian",
        "kali": "debian",
        "linuxmint": "debian",
        "fedora": "rhel",
        "rocky": "rhel",
        "opensuse-leap": "suse",
        "opensuse-tumbleweed": "suse",
        "arch": "arch",
        "manjaro": "arch",
        "alpine": "alpine",
    }
    for distro_id, expected in cases.items():
        assert _family(_os_release(distro_id)) == expected, distro_id


def test_family_detection_by_id_like() -> None:
    assert _family(_os_release("pop", "ubuntu debian")) == "debian"
    assert _family(_os_release("endeavouros", "arch")) == "arch"
    assert _family(_os_release("bazzite", "fedora")) == "rhel"
    assert _family(_os_release("nixos", "")) == "unknown"


def test_os_name_falls_back_gracefully() -> None:
    assert _run("zh_os_name", "")  # no os-release content must not crash


def test_zh_deps_are_family_specific_and_cover_runtime_tools() -> None:
    common = {"nftables", "curl", "git", "tar", "gzip", "ca-certificates"}
    for distro_id in ("debian", "fedora", "opensuse-leap", "arch"):
        deps = _run("zh_deps", _os_release(distro_id)).split()
        assert common.issubset(set(deps)), distro_id
    debian_deps = _run("zh_deps", _os_release("debian")).split()
    assert "polkitd" in debian_deps
    assert "pkexec" in debian_deps
    assert "policykit-1" not in debian_deps
    assert "polkit" in _run("zh_deps", _os_release("fedora")).split()
    assert "polkit" in _run("zh_deps", _os_release("arch")).split()
    assert "python" in _run("zh_deps", _os_release("arch")).split()
    assert _run("zh_deps", _os_release("alpine")) == ""
    assert "nodejs-default" in _run("zh_deps", _os_release("opensuse-leap")).split()


def test_zh_pkg_manager_matches_family() -> None:
    non_atomic = {"ZH_ATOMIC": "0"}
    assert _run("zh_pkg_manager", _os_release("debian")) == "apt-get"
    assert (
        _run("zh_pkg_manager", _os_release("fedora"), {**non_atomic, "ZH_RHEL_MANAGER": "dnf"})
        == "dnf"
    )
    assert (
        _run("zh_pkg_manager", _os_release("fedora"), {**non_atomic, "ZH_RHEL_MANAGER": "yum"})
        == "yum"
    )
    assert _run("zh_pkg_manager", _os_release("opensuse-leap")) == "zypper"
    assert _run("zh_pkg_manager", _os_release("arch")) == "pacman"
    assert _run("zh_pkg_manager", _os_release("alpine")) == "apk"


def test_atomic_rhel_uses_rpm_ostree_instead_of_dnf() -> None:
    atomic = {"ZH_ATOMIC": "1"}
    assert _run("zh_is_atomic && echo yes || echo no", _os_release("fedora"), atomic) == "yes"
    assert _run("zh_pkg_manager", _os_release("bazzite", "fedora"), atomic) == "rpm-ostree"
    install_cmd = _run("zh_pkg_install_cmd foo bar", _os_release("fedora"), atomic)
    assert install_cmd == "rpm-ostree install foo bar"
    local_cmd = _run("zh_pkg_install_cmd ./happ.rpm", _os_release("fedora"), atomic)
    assert local_cmd == "rpm-ostree install ./happ.rpm"
    assert _run("zh_pkg_manager", _os_release("bazzite", "fedora")) in ("rpm-ostree", "dnf")


def test_non_atomic_install_cmd_matches_manager() -> None:
    non_atomic = {"ZH_ATOMIC": "0"}
    assert (
        _run(
            "zh_pkg_install_cmd foo bar",
            _os_release("fedora"),
            {**non_atomic, "ZH_RHEL_MANAGER": "dnf"},
        )
        == "dnf install -y foo bar"
    )
    assert _run("zh_pkg_install_cmd foo bar", _os_release("debian")) == "apt-get install -y foo bar"


def test_zh_arch_returns_non_empty() -> None:
    assert _run("zh_arch", _os_release("debian"))
