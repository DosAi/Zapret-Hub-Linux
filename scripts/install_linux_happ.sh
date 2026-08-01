#!/bin/sh
set -eu

DRY_RUN=0
HAPP_VERSION=3.3.6

usage() {
    cat <<'EOF'
Usage: install_linux_happ.sh [--dry-run]

Installs the pinned official Happ package on Kali/Debian when Happ is absent.
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

ARCH=$(dpkg --print-architecture 2>/dev/null || uname -m)
case "$ARCH" in
    amd64|x86_64)
        ASSET=Happ.linux.x64.deb
        SHA256=a7dac51277387bfe1049b1ad40f40f2e74af233a5eab020b5be1a622effc46a4
        ;;
    arm64|aarch64)
        ASSET=Happ.linux.arm64.deb
        SHA256=a4d3d6dcab1db61db23cdf0f86bce736014887262b570927befe48cb49f14aa6
        ;;
    *)
        echo "Happ $HAPP_VERSION does not provide a Debian package for architecture: $ARCH" >&2
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

if dpkg-query -W -f='${Status}' happ 2>/dev/null | grep -q 'install ok installed'; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' happ 2>/dev/null || true)
    echo "Existing Happ $INSTALLED_VERSION found; preserving it without restart or upgrade."
    exit 0
fi

PACKAGE=$(mktemp "/tmp/zapret-hub-happ-$HAPP_VERSION.XXXXXX.deb")
cleanup() {
    case "$PACKAGE" in /tmp/zapret-hub-happ-*.deb) rm -f -- "$PACKAGE" ;; esac
}
trap cleanup EXIT HUP INT TERM

curl -fL --retry 3 --connect-timeout 20 "$URL" -o "$PACKAGE"
printf '%s  %s\n' "$SHA256" "$PACKAGE" | sha256sum -c -
apt-get install -y "$PACKAGE"

echo "Installed official Happ $HAPP_VERSION. No VPN connection was selected or started by Zapret Hub."
