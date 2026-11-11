#!/bin/sh
set -eu

DRY_RUN=0
REMOVE_HAPP=0

usage() {
    cat <<'EOF'
Usage: uninstall_linux_system.sh [--dry-run] [--remove-happ]

Root-only helper used by uninstall.sh. It removes only Zapret Hub-owned system
integration and installations carrying a .zapret-hub-managed marker. Existing
third-party Zapret installations and shared distribution packages are kept.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --remove-happ) REMOVE_HAPP=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck disable=SC1091
. "$SCRIPT_DIR/lib/distro.sh"

FAMILY=$(zh_distro_family)
case "$FAMILY" in
    debian|rhel|suse|arch) ;;
    *) echo "Unsupported distribution family: $FAMILY" >&2; exit 1 ;;
esac

if [ "$DRY_RUN" -ne 1 ] && [ "$(id -u)" -ne 0 ]; then
    echo "This helper must run as root; use ./uninstall.sh instead." >&2
    exit 1
fi

remove_unit() {
    unit=$1
    unit_path="/etc/systemd/system/$unit"
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] disable, stop and remove $unit when owned by Zapret Hub"
        return
    fi
    systemctl disable --now "$unit" >/dev/null 2>&1 || true
    rm -f -- "$unit_path"
}

CLASSIC_UNIT=/etc/systemd/system/zapret_discord_youtube.service
if [ "$DRY_RUN" -eq 1 ]; then
    remove_unit zapret_discord_youtube.service
elif [ -f "$CLASSIC_UNIT" ] && grep -qF 'managed by Zapret Hub' "$CLASSIC_UNIT"; then
    remove_unit zapret_discord_youtube.service
else
    echo "Preserving unmanaged classic Zapret systemd unit."
fi

for classic_root in \
    /opt/zapret-discord-youtube-linux \
    /opt/zapret-hub/zapret-discord-youtube-linux
do
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] remove $classic_root only when .zapret-hub-managed exists"
    elif [ -f "$classic_root/.zapret-hub-managed" ]; then
        rm -rf -- "$classic_root"
        echo "Removed managed classic Zapret installation: $classic_root"
    elif [ -e "$classic_root" ]; then
        echo "Preserving unmanaged classic Zapret installation: $classic_root"
    fi
done

ZAPRET2_ROOT=/opt/zapret2
if [ "$DRY_RUN" -eq 1 ]; then
    remove_unit zapret2.service
    echo "[dry-run] remove $ZAPRET2_ROOT only when .zapret-hub-managed exists"
elif [ -f "$ZAPRET2_ROOT/.zapret-hub-managed" ]; then
    remove_unit zapret2.service
    rm -rf -- "$ZAPRET2_ROOT"
    echo "Removed the managed Zapret2 installation."
elif [ -e "$ZAPRET2_ROOT" ]; then
    echo "Preserving unmanaged Zapret2 installation and its systemd unit."
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] remove /etc/polkit-1/rules.d/49-zapret-hub.rules"
else
    rm -f -- /etc/polkit-1/rules.d/49-zapret-hub.rules
fi

if [ "$REMOVE_HAPP" -eq 1 ]; then
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] $(zh_pkg_manager) remove the happ package"
    elif zh_pkg_installed happ; then
        zh_pkg_remove happ
        echo "Removed Happ at the user's explicit request."
    else
        echo "Happ is not installed."
    fi
else
    echo "Preserving Happ (use --remove-happ to remove it explicitly)."
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] remove Zapret Hub system ownership records and reload systemd"
else
    rm -rf -- /var/lib/zapret-hub
    systemctl daemon-reload
fi
