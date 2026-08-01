#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
cd "$PROJECT_ROOT"

if [[ ! -x .venv/bin/zapret-hub ]]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 is missing. Run ./scripts/install_linux.sh first." >&2
    exit 2
  fi
  python3 -m venv .venv
  .venv/bin/python -m pip install -e .
fi

if [[ ! -f web_ui/dist/index.html ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Frontend is not built. Install nodejs and npm, then run this script again." >&2
    exit 2
  fi
  (
    cd web_ui
    npm ci
    npm run build
  )
fi

exec .venv/bin/zapret-hub "$@"
