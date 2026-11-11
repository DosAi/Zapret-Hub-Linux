#!/bin/sh
set -eu

SOURCE=
VERSION=
TARGET=${ZAPRET_HUB_ZAPRET2_ROOT:-/opt/zapret2}
SERVICE=${ZAPRET_HUB_ZAPRET2_SERVICE:-zapret2.service}
DRY_RUN=0

usage() {
    cat <<'EOF'
Usage: update_linux_zapret2_system.sh --source PATH --version VERSION [--target PATH] [--dry-run]

Root helper used by Zapret Hub to update a Hub-managed Zapret2 installation.
The helper stages and validates the new tree, preserves local configuration,
restores the previous tree on failure, and returns the service to its prior state.
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --source) [ "$#" -ge 2 ] || exit 2; SOURCE=$2; shift 2 ;;
        --version) [ "$#" -ge 2 ] || exit 2; VERSION=$2; shift 2 ;;
        --target) [ "$#" -ge 2 ] || exit 2; TARGET=$2; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -n "$SOURCE" ] || { echo "--source is required" >&2; exit 2; }
[ -n "$VERSION" ] || { echo "--version is required" >&2; exit 2; }
[ -d "$SOURCE" ] || { echo "Zapret2 source directory does not exist: $SOURCE" >&2; exit 1; }

case "$TARGET" in
    /opt/*) ;;
    *) echo "Refusing a target outside /opt: $TARGET" >&2; exit 1 ;;
esac
case "$SERVICE" in
    *[!A-Za-z0-9_.@-]*|'') echo "Invalid systemd service name" >&2; exit 1 ;;
esac

if [ ! -f "$TARGET/.zapret-hub-managed" ]; then
    echo "Refusing to update unmanaged Zapret2 installation: $TARGET" >&2
    exit 1
fi

find_linux_binary() {
    root=$1
    machine=$(uname -m)
    case "$machine" in
        x86_64|amd64) arch=x86_64 ;;
        aarch64|arm64) arch=arm64 ;;
        i?86) arch=x86 ;;
        armv7l|armv7*) arch=arm ;;
        *) arch=$machine ;;
    esac
    for candidate in \
        "$root/binaries/my/nfqws2" \
        "$root/binaries/linux-$arch/nfqws2" \
        "$root/nfq2/nfqws2" \
        "$root/nfqws2"
    do
        [ -f "$candidate" ] && { printf '%s\n' "$candidate"; return 0; }
    done
    return 1
}

find_linux_binary "$SOURCE" >/dev/null || {
    echo "Downloaded Zapret2 tree has no nfqws2 binary for this architecture." >&2
    exit 1
}
[ -f "$SOURCE/install_bin.sh" ] || {
    echo "Downloaded Zapret2 tree has no install_bin.sh." >&2
    exit 1
}

PARENT=$(dirname -- "$TARGET")
BASE=$(basename -- "$TARGET")
STAGE="$PARENT/.${BASE}.zapret-hub-stage.$$"
BACKUP="$PARENT/.${BASE}.zapret-hub-backup"
OLD_BACKUP="$PARENT/.${BASE}.zapret-hub-backup.old"
WAS_ACTIVE=0
SWAPPED=0

if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet "$SERVICE"; then
    WAS_ACTIVE=1
fi

if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] stage Zapret2 $VERSION from $SOURCE in $STAGE"
    echo "[dry-run] preserve config and user-owned ipset files from $TARGET"
    [ "$WAS_ACTIVE" -eq 0 ] || echo "[dry-run] stop and later restart $SERVICE"
    echo "[dry-run] atomically replace the managed tree and keep rollback backup at $BACKUP"
    exit 0
fi

[ "$(id -u)" -eq 0 ] || {
    echo "This helper must run as root (Zapret Hub normally starts it through pkexec)." >&2
    exit 1
}

cleanup_stage() {
    [ ! -e "$STAGE" ] || rm -rf -- "$STAGE"
}

rollback() {
    code=$?
    trap - EXIT HUP INT TERM
    cleanup_stage
    if [ "$SWAPPED" -eq 1 ] && [ -d "$BACKUP" ]; then
        rm -rf -- "$TARGET"
        mv -- "$BACKUP" "$TARGET"
        command -v systemctl >/dev/null 2>&1 && systemctl daemon-reload || true
        [ "$WAS_ACTIVE" -eq 0 ] || systemctl start "$SERVICE" || true
        echo "Zapret2 update failed; the previous installation was restored." >&2
    fi
    exit "$code"
}
trap rollback EXIT HUP INT TERM

cleanup_stage
mkdir -p -- "$STAGE"
cp -a -- "$SOURCE/." "$STAGE/"
touch "$STAGE/.zapret-hub-managed"
printf '%s\n' "$VERSION" > "$STAGE/.zapret-hub-version"

# Configuration and user-maintained lists belong to the installation, not to a
# release archive. Preserve them without carrying old binaries into the stage.
if [ -f "$TARGET/config" ]; then
    cp -a -- "$TARGET/config" "$STAGE/config"
fi
if [ -d "$TARGET/ipset" ]; then
    mkdir -p -- "$STAGE/ipset"
    for item in "$TARGET"/ipset/zapret-hosts-user*.txt "$TARGET"/ipset/*-user.txt; do
        [ -f "$item" ] || continue
        cp -a -- "$item" "$STAGE/ipset/"
    done
fi
if [ -d "$TARGET/init.d/custom.d" ]; then
    mkdir -p -- "$STAGE/init.d"
    rm -rf -- "$STAGE/init.d/custom.d"
    cp -a -- "$TARGET/init.d/custom.d" "$STAGE/init.d/custom.d"
fi

[ ! -d "$STAGE/binaries" ] || find "$STAGE/binaries" -type f -exec chmod 0755 {} +
[ ! -d "$STAGE/init.d" ] || find "$STAGE/init.d" -type f -exec chmod 0755 {} +
[ ! -d "$STAGE/ipset" ] || find "$STAGE/ipset" -type f -name '*.sh' -exec chmod 0755 {} +
[ ! -d "$STAGE/common" ] || find "$STAGE/common" -type f -name '*.sh' -exec chmod 0755 {} +
chmod 0755 "$STAGE/install_bin.sh"
ZAPRET_BASE="$STAGE" /bin/sh "$STAGE/install_bin.sh"
find_linux_binary "$STAGE" >/dev/null
chown -R root:root "$STAGE"

if [ "$WAS_ACTIVE" -eq 1 ]; then
    systemctl stop "$SERVICE"
fi

rm -rf -- "$OLD_BACKUP"
[ ! -d "$BACKUP" ] || mv -- "$BACKUP" "$OLD_BACKUP"
mv -- "$TARGET" "$BACKUP"
SWAPPED=1
mv -- "$STAGE" "$TARGET"

if [ -f "$TARGET/init.d/systemd/zapret2.service" ]; then
    install -o root -g root -m 0644 "$TARGET/init.d/systemd/zapret2.service" /etc/systemd/system/zapret2.service
fi
systemctl daemon-reload
if [ "$WAS_ACTIVE" -eq 1 ]; then
    systemctl start "$SERVICE"
    systemctl is-active --quiet "$SERVICE"
fi

SWAPPED=0
rm -rf -- "$OLD_BACKUP"
trap - EXIT HUP INT TERM
echo "Zapret2 $VERSION was installed in $TARGET. Previous tree: $BACKUP"
