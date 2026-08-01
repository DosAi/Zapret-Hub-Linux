#!/bin/sh
set -eu

DRY_RUN=0
PROJECT_ROOT=

# Stable upstream release. The archive hash is checked before any file from it
# is executed as root. Its own dependency command pins nfqws and strategies too.
ADAPTER_REVISION=2136b8199474233f8018bc696fa97ef5d49320ff
ADAPTER_SHA256=105c9088da598936593ff6a52cbf4759ccea15cfe149c4254f9cdece919365a7
ADAPTER_URL="https://codeload.github.com/Sergeydigl3/zapret-discord-youtube-linux/tar.gz/$ADAPTER_REVISION"
STANDARD_TARGET=/opt/zapret-discord-youtube-linux
FALLBACK_TARGET=/opt/zapret-hub/zapret-discord-youtube-linux

usage() {
    cat <<'EOF'
Usage: install_linux_classic_zapret.sh --project-root PATH [--dry-run]

Installs the pinned zapret-discord-youtube-linux adapter and registers its
systemd unit. It never starts, stops, restarts, enables, or disables a service.
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
UNIT_TEMPLATE="$PROJECT_ROOT/packaging/linux/zapret_discord_youtube.service.in"
[ -r "$UNIT_TEMPLATE" ] || { echo "Missing systemd template: $UNIT_TEMPLATE" >&2; exit 1; }

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] install classic Zapret for Linux release 0.5.0 in /opt (preserve foreign installs)"
    echo "[dry-run] verify classic Zapret source archive SHA-256 before executing it"
    echo "[dry-run] download pinned nfqws v72.9 and pinned Flowseal strategies"
    echo "[dry-run] install zapret_discord_youtube.service without starting or restarting it"
    exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "This helper must run as root; use scripts/install_linux.sh instead." >&2
    exit 1
fi

is_ready_install() {
    [ -x "$1/service.sh" ] && [ -x "$1/nfqws" ] && [ -d "$1/zapret-latest" ]
}

CLASSIC_ROOT=
if is_ready_install "$STANDARD_TARGET" && [ ! -f "$STANDARD_TARGET/.zapret-hub-managed" ]; then
    CLASSIC_ROOT=$STANDARD_TARGET
    echo "Using the existing unmanaged classic Zapret installation in $CLASSIC_ROOT."
elif [ ! -e "$STANDARD_TARGET" ] || [ -f "$STANDARD_TARGET/.zapret-hub-managed" ]; then
    CLASSIC_ROOT=$STANDARD_TARGET
else
    CLASSIC_ROOT=$FALLBACK_TARGET
    echo "Existing unmanaged $STANDARD_TARGET is incomplete; preserving it and using $CLASSIC_ROOT."
fi

MANAGED_MARKER="$CLASSIC_ROOT/.zapret-hub-managed"
if ! is_ready_install "$CLASSIC_ROOT" || [ -f "$MANAGED_MARKER" ]; then
    if ! is_ready_install "$CLASSIC_ROOT"; then
        ARCHIVE=$(mktemp /tmp/zapret-hub-classic.XXXXXX.tar.gz)
        STAGING=$(mktemp -d /tmp/zapret-hub-classic.XXXXXX)
        cleanup() {
            case "$ARCHIVE" in /tmp/zapret-hub-classic.*.tar.gz) rm -f -- "$ARCHIVE" ;; esac
            case "$STAGING" in /tmp/zapret-hub-classic.*) rm -rf -- "$STAGING" ;; esac
        }
        trap cleanup EXIT HUP INT TERM

        curl -fL --retry 3 --connect-timeout 20 "$ADAPTER_URL" -o "$ARCHIVE"
        printf '%s  %s\n' "$ADAPTER_SHA256" "$ARCHIVE" | sha256sum -c -
        tar -xzf "$ARCHIVE" -C "$STAGING" --strip-components=1
        chmod 0755 "$STAGING/service.sh"
        find "$STAGING/src" -type f -name '*.sh' -exec chmod 0755 {} +

        # This is deliberately non-interactive and downloads versions pinned by
        # the selected upstream adapter release.
        (
            cd "$STAGING"
            HOME=/root /bin/bash ./service.sh download-deps --default
        )
        [ -x "$STAGING/nfqws" ] || { echo "Classic Zapret nfqws was not prepared" >&2; exit 1; }
        [ -f "$STAGING/zapret-latest/general.bat" ] || { echo "Classic Zapret strategies were not prepared" >&2; exit 1; }

        install -d -o root -g root -m 0755 "$CLASSIC_ROOT"
        cp -a "$STAGING/." "$CLASSIC_ROOT/"
        touch "$MANAGED_MARKER"
        chown -R root:root "$CLASSIC_ROOT"
        echo "Installed classic Zapret for Linux in $CLASSIC_ROOT."
    else
        echo "Managed classic Zapret installation in $CLASSIC_ROOT is already complete."
    fi
fi

if [ ! -f "$CLASSIC_ROOT/conf.env" ]; then
    cat > "$CLASSIC_ROOT/conf.env" <<'EOF'
# Initial profile installed by Zapret Hub. Change it through the upstream tools
# if another classic Zapret strategy works better for your provider.
strategy=general.bat
interface=any
gamefiltertcp=false
gamefilterudp=false
firewall_backend=nftables
EOF
    chown root:root "$CLASSIC_ROOT/conf.env"
    chmod 0644 "$CLASSIC_ROOT/conf.env"
fi

UNIT_TARGET=/etc/systemd/system/zapret_discord_youtube.service
if [ ! -f "$UNIT_TARGET" ] || grep -q "managed by Zapret Hub" "$UNIT_TARGET"; then
    UNIT_STAGING=$(mktemp /tmp/zapret-hub-classic-unit.XXXXXX)
    sed "s|@CLASSIC_ROOT@|$CLASSIC_ROOT|g" "$UNIT_TEMPLATE" > "$UNIT_STAGING"
    install -o root -g root -m 0644 "$UNIT_STAGING" "$UNIT_TARGET"
    rm -f -- "$UNIT_STAGING"
else
    echo "Existing unmanaged $UNIT_TARGET was found; preserving it."
fi

echo "Classic Zapret is installed and registered. Its service state was not changed."
