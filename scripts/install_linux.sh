#!/usr/bin/env bash
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
DISTRO_LIB="$PROJECT_ROOT/scripts/lib/distro.sh"
SYSTEM_HELPER="$PROJECT_ROOT/scripts/install_linux_system.sh"
DRY_RUN=0
LAUNCH=1
INSTALL_TELEGRAM=0

usage() {
  cat <<'EOF'
Usage: ./scripts/install_linux.sh [--dry-run] [--no-launch] [--with-telegram]

Installs Zapret Hub, classic Zapret for Linux, bundled Zapret2, the
official Happ client, and the bundled TG WS Proxy on a supported Linux
distribution (Kali/Debian/Ubuntu, Fedora, Arch and openSUSE families).
The managed Zapret, Zapret2 and Happ services currently require systemd.
Alpine/OpenRC is detected but deliberately rejected instead of leaving a
partially working installation.
Administrator authorization is requested once. Existing foreign Zapret
installations and their configurations are preserved.
EOF
}

while (($#)); do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --no-launch) LAUNCH=0 ;;
    --with-telegram) INSTALL_TELEGRAM=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This installer supports Linux only." >&2
  exit 1
fi

if [[ ! -r "$DISTRO_LIB" ]]; then
  echo "The checkout is incomplete (scripts/lib/distro.sh is missing). Download or clone the complete fork instead of individual files." >&2
  exit 1
fi
# shellcheck disable=SC1091
. "$DISTRO_LIB"

FAMILY="$(zh_distro_family)"
if [[ "$FAMILY" == "unknown" ]]; then
  echo "Cannot identify this Linux distribution (/etc/os-release is missing or not supported)." >&2
  exit 1
fi

if [[ "$FAMILY" == "alpine" ]]; then
  echo "Alpine/OpenRC is not supported yet: the official Happ and PySide6 builds require a glibc/systemd-compatible environment." >&2
  exit 1
fi

if [[ ! -r "$SYSTEM_HELPER" || ! -r "$PROJECT_ROOT/runtime/zapret2/config.default" || ! -r "$PROJECT_ROOT/runtime/tg-ws-proxy/proxy/tg_ws_proxy.py" ]]; then
  echo "The checkout is incomplete. Download or clone the complete fork instead of individual files." >&2
  exit 1
fi

if ! zh_is_systemd; then
  if (( DRY_RUN )); then
    echo "WARNING: systemd is not active; this is only a package/distro preview." >&2
  else
    echo "systemd is required to manage Zapret, Zapret2 and Happ. Installation was not changed." >&2
    exit 1
  fi
fi

helper_args=(--project-root "$PROJECT_ROOT")
(( INSTALL_TELEGRAM == 1 )) && helper_args+=(--with-telegram)

if (( DRY_RUN )); then
  echo "Zapret Hub installation preview for: $PROJECT_ROOT"
  echo "Distribution: $(zh_os_name)"
  echo "Package family: $FAMILY"
  echo "Package manager: $(zh_pkg_manager)"
  /bin/sh "$SYSTEM_HELPER" "${helper_args[@]}" --dry-run
  echo "[dry-run] create $PROJECT_ROOT/.venv and install the Python application"
  echo "[dry-run] verify bundled TG WS Proxy and its Python dependencies"
  echo "[dry-run] npm ci && npm run build in $PROJECT_ROOT/web_ui"
  echo "[dry-run] create a per-user application launcher"
  (( LAUNCH == 0 )) || echo "[dry-run] launch Zapret Hub"
  exit 0
fi

if [[ "$(id -u)" -eq 0 ]]; then
  echo "Run this script as your desktop user, without sudo. It requests admin access once through PolicyKit." >&2
  exit 1
fi

if command -v pkexec >/dev/null 2>&1; then
  elevate=(pkexec)
elif command -v sudo >/dev/null 2>&1; then
  elevate=(sudo)
else
  echo "Either pkexec or sudo is required for the one-time system setup." >&2
  exit 1
fi

echo "Administrator authorization is needed once for packages, Zapret, Zapret2, Happ, and system integration."
"${elevate[@]}" /bin/sh "$SYSTEM_HELPER" "${helper_args[@]}"

cd "$PROJECT_ROOT"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
PYTHONPATH="$PROJECT_ROOT/runtime/tg-ws-proxy" .venv/bin/python -c \
  'from proxy import tg_ws_proxy; assert callable(tg_ws_proxy.main)'
echo "Bundled TG WS Proxy is ready."

(
  cd web_ui
  npm ci
  npm run build
)

USER_BIN="${HOME}/.local/bin"
USER_APPS="${XDG_DATA_HOME:-${HOME}/.local/share}/applications"
USER_ICONS="${XDG_DATA_HOME:-${HOME}/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$USER_BIN" "$USER_APPS" "$USER_ICONS"
ln -sfn "$PROJECT_ROOT/scripts/run_linux.sh" "$USER_BIN/zapret-hub"
install -m 0644 "$PROJECT_ROOT/ui_assets/icons/app.svg" "$USER_ICONS/zapret-hub.svg"

DESKTOP_FILE="$USER_APPS/zapret-hub.desktop"
{
  echo '[Desktop Entry]'
  echo 'Type=Application'
  echo 'Name=Zapret Hub'
  echo 'Comment=Manage Zapret, Zapret2, Happ and TG WS Proxy'
  printf 'Exec=%s/zapret-hub\n' "$USER_BIN"
  echo 'Icon=zapret-hub'
  echo 'Terminal=false'
  echo 'Categories=Network;Utility;'
  echo 'StartupNotify=true'
} > "$DESKTOP_FILE"
chmod 0644 "$DESKTOP_FILE"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$USER_APPS" >/dev/null 2>&1 || true

echo
echo "Zapret Hub is installed. Zapret, Zapret2, Happ, and TG WS Proxy are ready; the installer did not change the current VPN or network session."
echo "Launch it later with: $USER_BIN/zapret-hub"

if (( LAUNCH )); then
  exec "$USER_BIN/zapret-hub"
fi
