#!/bin/sh
set -eu

DRY_RUN=0
INSTALL_TELEGRAM=0
PROJECT_ROOT=

usage() {
    cat <<'EOF'
Usage: install_linux_system.sh --project-root PATH [--dry-run] [--with-telegram]

Root-only helper for install_linux.sh. It installs the distribution packages
for the detected family (Kali/Debian/Ubuntu, Fedora, Arch or openSUSE),
classic Zapret for Linux, the bundled Zapret2 backend, their systemd units
(when systemd is present), and the narrow Zapret Hub PolicyKit rule. It
deliberately does not start, stop, restart, enable, or disable any network
service.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --project-root)
            [ "$#" -ge 2 ] || { echo "--project-root requires a path" >&2; exit 2; }
            PROJECT_ROOT=$2
            shift 2
            ;;
        --dry-run)
            DRY_RUN=1
            shift
            ;;
        --with-telegram)
            INSTALL_TELEGRAM=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

[ -n "$PROJECT_ROOT" ] || { echo "--project-root is required" >&2; exit 2; }
PROJECT_ROOT=$(CDPATH= cd -- "$PROJECT_ROOT" && pwd)

DISTRO_LIB="$PROJECT_ROOT/scripts/lib/distro.sh"
[ -r "$DISTRO_LIB" ] || { echo "scripts/lib/distro.sh is missing; the checkout is incomplete." >&2; exit 1; }
# shellcheck disable=SC1091
. "$DISTRO_LIB"

ZAPRET_SOURCE="$PROJECT_ROOT/runtime/zapret2"
CLASSIC_HELPER="$PROJECT_ROOT/scripts/install_linux_classic_zapret.sh"
HAPP_HELPER="$PROJECT_ROOT/scripts/install_linux_happ.sh"
POLKIT_SOURCE="$PROJECT_ROOT/packaging/polkit/49-zapret-hub.rules"
HOSTLIST_SOURCE="$PROJECT_ROOT/packaging/linux/zapret-hosts-user.txt"

for required in \
    "$ZAPRET_SOURCE/config.default" \
    "$ZAPRET_SOURCE/install_bin.sh" \
    "$ZAPRET_SOURCE/init.d/sysv/zapret2" \
    "$ZAPRET_SOURCE/init.d/systemd/zapret2.service" \
    "$CLASSIC_HELPER" \
    "$HAPP_HELPER" \
    "$POLKIT_SOURCE" \
    "$HOSTLIST_SOURCE"
do
    [ -r "$required" ] || { echo "Required installation file is missing: $required" >&2; exit 1; }
done

FAMILY=$(zh_distro_family)
if [ "$FAMILY" = "unknown" ]; then
    echo "Cannot identify this Linux distribution (/etc/os-release is missing or not supported)." >&2
    exit 1
fi
if [ "$FAMILY" = "alpine" ]; then
    echo "Alpine/OpenRC is not supported yet; refusing a partial installation." >&2
    exit 1
fi
if [ "$DRY_RUN" -ne 1 ] && ! zh_is_systemd; then
    echo "systemd is required to install the managed Zapret, Zapret2 and Happ services." >&2
    exit 1
fi

PACKAGES=$(zh_deps)
[ -n "$PACKAGES" ] || { echo "No package list for distribution family: $FAMILY" >&2; exit 1; }

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] distribution family: $FAMILY"
    echo "[dry-run] $(zh_pkg_manager) update"
    echo "[dry-run] $(zh_pkg_install_cmd $PACKAGES)"
    if [ "$INSTALL_TELEGRAM" -eq 1 ]; then
        echo "[dry-run] $(zh_pkg_install_cmd telegram-desktop)"
    fi
    /bin/sh "$CLASSIC_HELPER" --project-root "$PROJECT_ROOT" --dry-run
    /bin/sh "$HAPP_HELPER" --dry-run
    echo "[dry-run] install bundled Zapret2 in /opt/zapret2 (preserve foreign installs)"
    if zh_is_systemd; then
        echo "[dry-run] install zapret2.service without starting or restarting it"
        echo "[dry-run] install /etc/polkit-1/rules.d/49-zapret-hub.rules"
    else
        echo "[dry-run] systemd not found; skip service units and the PolicyKit rule"
    fi
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "This helper must run as root; use scripts/install_linux.sh instead." >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive
zh_pkg_update
# shellcheck disable=SC2086
zh_pkg_install $PACKAGES

if zh_is_atomic; then
    echo "NOTE: this is an immutable (rpm-ostree) system; the packages above were layered for the next boot. Anything that depends on them becomes available after a reboot."
fi

if [ "$INSTALL_TELEGRAM" -eq 1 ]; then
    if ! zh_pkg_install telegram-desktop; then
        echo "WARNING: telegram-desktop could not be installed; continuing without it." >&2
    fi
fi

/bin/sh "$CLASSIC_HELPER" --project-root "$PROJECT_ROOT"
/bin/sh "$HAPP_HELPER"

ZAPRET_TARGET=/opt/zapret2
MANAGED_MARKER="$ZAPRET_TARGET/.zapret-hub-managed"

MANAGED_INSTALL=0
if [ ! -d "$ZAPRET_TARGET" ] || [ -f "$MANAGED_MARKER" ]; then
    MANAGED_INSTALL=1
    install -d -o root -g root -m 0755 "$ZAPRET_TARGET"
    cp -a "$ZAPRET_SOURCE/." "$ZAPRET_TARGET/"
    touch "$MANAGED_MARKER"
    chown -R root:root "$ZAPRET_TARGET"
    echo "Installed the bundled Zapret2 backend in $ZAPRET_TARGET."
else
    echo "Existing unmanaged $ZAPRET_TARGET was found; preserving its files and configuration."
fi

# Git archives do not always preserve the executable bits of the bundled
# cross-platform release. Make scripts and prebuilt binaries runnable before
# asking upstream's architecture detector to create nfq2/ip2net/mdig links.
[ -d "$ZAPRET_TARGET/binaries" ] && find "$ZAPRET_TARGET/binaries" -type f -exec chmod 0755 {} +
[ -d "$ZAPRET_TARGET/init.d" ] && find "$ZAPRET_TARGET/init.d" -type f -exec chmod 0755 {} +
[ -d "$ZAPRET_TARGET/ipset" ] && find "$ZAPRET_TARGET/ipset" -type f -name '*.sh' -exec chmod 0755 {} +
[ -d "$ZAPRET_TARGET/common" ] && find "$ZAPRET_TARGET/common" -type f -name '*.sh' -exec chmod 0755 {} +
chmod 0755 "$ZAPRET_TARGET/install_bin.sh"

ZAPRET_BASE="$ZAPRET_TARGET" /bin/sh "$ZAPRET_TARGET/install_bin.sh"

if [ ! -f "$ZAPRET_TARGET/config" ]; then
    WAN_INTERFACE=
    for candidate in $(ip -4 route show default 2>/dev/null | awk '{for (i=1; i<=NF; i++) if ($i == "dev") print $(i+1)}'); do
        case "$candidate" in
            lo|tun*|tap*|wg*|tailscale*|docker*|br-*|virbr*|veth*) continue ;;
        esac
        WAN_INTERFACE=$candidate
        break
    done

    {
        echo '# Linux desktop profile managed by Zapret Hub.'
        echo '# Keep upstream defaults in one place and override only host-specific settings.'
        echo '. "${ZAPRET_BASE:-/opt/zapret2}/config.default"'
        echo
        # Prefer nftables when available; otherwise leave FWTYPE unset so the
        # bundled backend falls back to iptables automatically.
        if command -v nft >/dev/null 2>&1; then
            echo 'FWTYPE=nftables'
        fi
        echo 'NFQWS2_ENABLE=1'
        echo 'MODE_FILTER=hostlist'
        echo 'FLOWOFFLOAD=none'
        if [ -n "$WAN_INTERFACE" ]; then
            printf 'IFACE_WAN=%s\n' "$WAN_INTERFACE"
            printf 'IFACE_WAN6=%s\n' "$WAN_INTERFACE"
        fi
        echo 'DISABLE_IPV6=1'
        echo 'INIT_APPLY_FW=1'
    } > "$ZAPRET_TARGET/config"
    chown root:root "$ZAPRET_TARGET/config"
    chmod 0644 "$ZAPRET_TARGET/config"
fi

if [ ! -f "$ZAPRET_TARGET/ipset/zapret-hosts-user.txt" ]; then
    install -o root -g root -m 0644 "$HOSTLIST_SOURCE" "$ZAPRET_TARGET/ipset/zapret-hosts-user.txt"
fi

if zh_is_systemd; then
    if [ "$MANAGED_INSTALL" -eq 1 ] || [ ! -f /etc/systemd/system/zapret2.service ]; then
        install -o root -g root -m 0644 \
            "$ZAPRET_SOURCE/init.d/systemd/zapret2.service" \
            /etc/systemd/system/zapret2.service
    fi
    install -d -o root -g root -m 0755 /etc/polkit-1/rules.d
    install -o root -g root -m 0644 \
        "$POLKIT_SOURCE" \
        /etc/polkit-1/rules.d/49-zapret-hub.rules

    systemctl daemon-reload
    echo "System integration (systemd and PolicyKit) is ready. No network service was started, stopped, restarted, enabled, or disabled."
else
    echo "systemd was not found; skipped the systemd service units and the PolicyKit rule. No network service was started, stopped, restarted, enabled, or disabled."
fi
