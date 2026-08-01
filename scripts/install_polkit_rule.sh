#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SOURCE_RULE="$PROJECT_ROOT/packaging/polkit/49-zapret-hub.rules"
TARGET_RULE=/etc/polkit-1/rules.d/49-zapret-hub.rules

if [ ! -r "$SOURCE_RULE" ]; then
    echo "PolicyKit rule not found: $SOURCE_RULE" >&2
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    install -o root -g root -m 0644 "$SOURCE_RULE" "$TARGET_RULE"
elif command -v pkexec >/dev/null 2>&1; then
    exec pkexec /usr/bin/install -o root -g root -m 0644 "$SOURCE_RULE" "$TARGET_RULE"
else
    echo "pkexec is required to install $TARGET_RULE" >&2
    exit 1
fi
