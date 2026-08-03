#!/bin/sh
set -eu

DRY_RUN=0
HAPP_VERSION=3.3.6
PACKAGE=

usage() {
    cat <<'EOF'
Usage: install_linux_happ.sh [--dry-run]

Installs the pinned official Happ package for the detected distribution
family (.deb on Debian/Ubuntu, .rpm on Fedora/RHEL/openSUSE, .pkg.tar.zst on
Arch) when Happ is absent. Alpine/OpenRC is intentionally unsupported because
the official Happ build targets glibc and its managed daemon targets systemd.
An existing Happ installation is always preserved to avoid interrupting an
active tunnel during install or upgrade.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/distro.sh"

FAMILY=$(zh_distro_family)
ARCH=$(zh_arch)

case "$FAMILY" in
    alpine)
        echo "Alpine/OpenRC is not supported by the Happ installer." >&2
        exit 1
        ;;
    debian)
        PACKAGE_SUFFIX=.deb
        case "$ARCH" in
            x86_64)
                ASSET=Happ.linux.x64.deb
                SHA256=a7dac51277387bfe1049b1ad40f40f2e74af233a5eab020b5be1a622effc46a4
                ;;
            aarch64)
                ASSET=Happ.linux.arm64.deb
                SHA256=a4d3d6dcab1db61db23cdf0f86bce736014887262b570927befe48cb49f14aa6
                ;;
            *)
                echo "Happ $HAPP_VERSION does not provide a Debian package for architecture: $ARCH" >&2
                exit 1
                ;;
        esac
        ;;
    rhel|suse)
        PACKAGE_SUFFIX=.rpm
        case "$ARCH" in
            x86_64)
                ASSET=Happ.linux.x64.rpm
                SHA256=bf7078723cd0761ea929edbc75fb6d10464920691f7cdcec47579254c3410d9b
                ;;
            aarch64)
                ASSET=Happ.linux.arm64.rpm
                SHA256=300c762a2e6d08773b6f4432f207f7dcb42ade8c2565738a06b4c18dfa2b3b94
                ;;
            *)
                echo "Happ $HAPP_VERSION does not provide an RPM package for architecture: $ARCH" >&2
                exit 1
                ;;
        esac
        ;;
    arch)
        PACKAGE_SUFFIX=.pkg.tar.zst
        case "$ARCH" in
            x86_64)
                ASSET=Happ.linux.x64.pkg.tar.zst
                SHA256=30eafd999ad5a99c7cb8ea780c4269f7fe6c4eedb1df50234e4fb44aa0c7d8a7
                ;;
            aarch64)
                ASSET=Happ.linux.arm64.pkg.tar.zst
                SHA256=25c8ea919902d6ed6deabf82b49184bbf5626fff88e4956cf65e5327388f28eb
                ;;
            *)
                echo "Happ $HAPP_VERSION does not provide an Arch package for architecture: $ARCH" >&2
                exit 1
                ;;
        esac
        ;;
    *)
        echo "Unsupported distribution family for Happ: $FAMILY" >&2
        exit 1
        ;;
esac

URL="https://github.com/Happ-proxy/happ-desktop/releases/download/$HAPP_VERSION/$ASSET"

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] preserve an existing Happ installation and active tunnel"
    echo "[dry-run] otherwise install official Happ $HAPP_VERSION for $ARCH after SHA-256 verification"
    echo "[dry-run] do not connect or disconnect Happ during installation"
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "This helper must run as root; use scripts/install_linux.sh instead." >&2
    exit 1
fi

if zh_pkg_installed happ; then
    INSTALLED_VERSION=$(zh_pkg_version happ)
    echo "Existing Happ ${INSTALLED_VERSION:-} found; preserving it without restart or upgrade."
    exit 0
fi

cleanup() {
    case "$PACKAGE" in /tmp/zapret-hub-happ-*) rm -f -- "$PACKAGE" ;; esac
}
trap cleanup EXIT HUP INT TERM

PACKAGE=$(mktemp "/tmp/zapret-hub-happ-$HAPP_VERSION.XXXXXX$PACKAGE_SUFFIX")
curl -fL --retry 3 --connect-timeout 20 "$URL" -o "$PACKAGE"
printf '%s  %s\n' "$SHA256" "$PACKAGE" | sha256sum -c -

zh_pkg_install_local "$PACKAGE"
echo "Installed official Happ $HAPP_VERSION. No VPN connection was selected or started by Zapret Hub."
