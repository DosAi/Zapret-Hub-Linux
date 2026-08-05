#!/bin/sh
# Narrow pkexec helper for Zapret Hub: persist only the strategy line of a
# root-owned classic Zapret conf.env. Installed as /usr/local/sbin and owned by
# root, so users cannot modify it to escalate privileges.
#
# Usage: zapret-hub-set-strategy <conf.env path> <strategy-filename>
set -eu

CONF_FILE=$1
STRATEGY=$2

# Defense in depth: never accept path separators, shell metacharacters, or
# anything outside a plain .bat file name. POSIX sh cannot express
# parenthesized character classes in case globs, so validate with grep -E.
if ! printf '%s' "$STRATEGY" | grep -Eq '^[A-Za-z0-9_. ()-]+\.bat$'; then
    echo "invalid strategy" >&2
    exit 2
fi
[ -f "$CONF_FILE" ] || exit 2

if grep -q '^strategy=' "$CONF_FILE"; then
    sed -i "s|^strategy=.*|strategy=${STRATEGY}|" "$CONF_FILE"
else
    printf 'strategy=%s\n' "$STRATEGY" >> "$CONF_FILE"
fi
