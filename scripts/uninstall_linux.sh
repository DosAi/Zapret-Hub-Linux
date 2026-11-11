#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
SYSTEM_HELPER="$PROJECT_ROOT/scripts/uninstall_linux_system.sh"
DRY_RUN=0
REMOVE_HAPP=0
PURGE_DATA=0
CLI_MODE=0

usage() {
  cat <<'EOF'
Usage: ./uninstall.sh [--cli] [--dry-run] [--remove-happ] [--purge-data]

Starts the graphical Zapret Hub uninstaller by default. --cli enables the
terminal fallback. Shared distribution packages and the source checkout are
preserved. Happ is preserved unless --remove-happ is explicitly supplied.
EOF
}

while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --remove-happ) REMOVE_HAPP=1 ;;
    --purge-data) PURGE_DATA=1 ;;
    --cli) CLI_MODE=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This uninstaller supports Linux only." >&2
  exit 1
fi

if (( CLI_MODE == 0 && DRY_RUN == 0 )); then
  GUI_PYTHON="$PROJECT_ROOT/.venv/bin/python"
  GUI_INDEX="$PROJECT_ROOT/web_ui/dist/index.html"
  if [[ ! -x "$GUI_PYTHON" || ! -f "$GUI_INDEX" ]]; then
    echo "The graphical uninstaller is unavailable because the installed Python environment or Web UI is missing." >&2
    echo "Run ./uninstall.sh --cli for the terminal fallback." >&2
    exit 1
  fi
  exec "$GUI_PYTHON" -m zapret_hub.uninstaller
fi

if [[ ! -x "$SYSTEM_HELPER" ]]; then
  echo "The checkout is incomplete (scripts/uninstall_linux_system.sh is missing)." >&2
  exit 1
fi
if [[ "$(id -u)" -eq 0 && "$DRY_RUN" -ne 1 ]]; then
  echo "Run this script as the desktop user, without sudo. It requests admin access once." >&2
  exit 1
fi

helper_args=()
(( DRY_RUN == 1 )) && helper_args+=(--dry-run)
(( REMOVE_HAPP == 1 )) && helper_args+=(--remove-happ)

if (( DRY_RUN )); then
  "$SYSTEM_HELPER" "${helper_args[@]}"
else
  if command -v pkexec >/dev/null 2>&1; then
    elevate=(pkexec)
  elif command -v sudo >/dev/null 2>&1; then
    elevate=(sudo)
  else
    echo "Either pkexec or sudo is required for system cleanup." >&2
    exit 1
  fi
  echo "Administrator authorization is needed once to remove system integration."
  "${elevate[@]}" /bin/sh "$SYSTEM_HELPER" "${helper_args[@]}"
fi

if (( PURGE_DATA )); then
  STATE_DIRS=(data configs mods mods_zapret2 merged_runtime backups cache logs)
  if (( DRY_RUN )); then
    for name in "${STATE_DIRS[@]}"; do
      echo "[dry-run] remove user state $PROJECT_ROOT/$name"
    done
  else
    for name in "${STATE_DIRS[@]}"; do
      rm -rf -- "$PROJECT_ROOT/$name"
    done
  fi
fi

USER_BIN="${HOME}/.local/bin/zapret-hub"
UNINSTALL_BIN="${HOME}/.local/bin/zapret-hub-uninstall"
XDG_DATA_ROOT="${XDG_DATA_HOME:-${HOME}/.local/share}"
USER_APPS="$XDG_DATA_ROOT/applications"
USER_ICON="$XDG_DATA_ROOT/icons/hicolor/scalable/apps/zapret-hub.svg"
USER_STATE="$XDG_DATA_ROOT/zapret-hub"
XDG_CONFIG_ROOT="${XDG_CONFIG_HOME:-${HOME}/.config}"
AUTOSTART_FILE="$XDG_CONFIG_ROOT/autostart/zapret-hub.desktop"
OWNS_USER_INTEGRATION=0
if [[ -L "$USER_BIN" ]] && [[ "$(readlink -f "$USER_BIN")" == "$PROJECT_ROOT/scripts/run_linux.sh" ]]; then
  OWNS_USER_INTEGRATION=1
elif [[ -f "$USER_STATE/install-root" ]] && [[ "$(<"$USER_STATE/install-root")" == "$PROJECT_ROOT" ]]; then
  OWNS_USER_INTEGRATION=1
fi

remove_user_file() {
  local path=$1
  if (( DRY_RUN )); then
    echo "[dry-run] remove $path if present"
  else
    rm -f -- "$path"
  fi
}

if (( DRY_RUN )); then
  echo "[dry-run] remove $USER_BIN only if it points to this checkout"
elif [[ -L "$USER_BIN" ]] && [[ "$(readlink -f "$USER_BIN")" == "$PROJECT_ROOT/scripts/run_linux.sh" ]]; then
  rm -f -- "$USER_BIN"
elif [[ -e "$USER_BIN" || -L "$USER_BIN" ]]; then
  echo "Preserving $USER_BIN because it does not belong to this checkout."
fi

if (( DRY_RUN )); then
  echo "[dry-run] remove $UNINSTALL_BIN only if it points to this checkout"
elif (( OWNS_USER_INTEGRATION )) && [[ -L "$UNINSTALL_BIN" ]] && [[ "$(readlink -f "$UNINSTALL_BIN")" == "$PROJECT_ROOT/uninstall.sh" ]]; then
  rm -f -- "$UNINSTALL_BIN"
elif [[ -e "$UNINSTALL_BIN" || -L "$UNINSTALL_BIN" ]]; then
  echo "Preserving $UNINSTALL_BIN because it does not belong to this checkout."
fi

if (( DRY_RUN )); then
  remove_user_file "$USER_APPS/zapret-hub.desktop"
  remove_user_file "$USER_APPS/zapret-hub-uninstall.desktop"
  remove_user_file "$USER_ICON"
  remove_user_file "$AUTOSTART_FILE"
  echo "[dry-run] remove installer ownership record $USER_STATE"
elif (( OWNS_USER_INTEGRATION )); then
  remove_user_file "$USER_APPS/zapret-hub.desktop"
  remove_user_file "$USER_APPS/zapret-hub-uninstall.desktop"
  remove_user_file "$USER_ICON"
  remove_user_file "$AUTOSTART_FILE"
  rm -rf -- "$USER_STATE"
  command -v update-desktop-database >/dev/null 2>&1 \
    && update-desktop-database "$USER_APPS" >/dev/null 2>&1 || true
else
  echo "Preserving user launchers because they belong to another Zapret Hub checkout."
fi

echo
echo "Zapret Hub Linux integration has been removed."
if (( PURGE_DATA )); then
  echo "The source checkout was preserved: $PROJECT_ROOT"
  echo "Local settings, logs and generated data were removed."
else
  echo "The source checkout and its data were preserved: $PROJECT_ROOT"
  echo "Delete that directory manually only after saving any logs or configuration you need."
fi
if (( REMOVE_HAPP == 0 )); then
  echo "Happ was preserved. Use --remove-happ only if you also want to remove that package."
fi
