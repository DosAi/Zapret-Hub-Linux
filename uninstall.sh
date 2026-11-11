#!/bin/sh
set -eu

PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$PROJECT_ROOT/scripts/uninstall_linux.sh" "$@"
