#!/usr/bin/env bash
# scripts/setup_browser.sh
#
# Configure Gecko-based browsers (Zen Browser, Firefox, LibreWolf, Floorp, Waterfox)
# for direct Zapret DPI bypass in Russia (enables DoH Cloudflare, ECH, disables QUIC and proxy).

set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"

DRY_RUN=0
REVERT=0

usage() {
    cat <<'USAGE'
Usage: ./scripts/setup_browser.sh [--dry-run] [--revert]

Configures browser profiles (Zen Browser, Firefox, LibreWolf, Floorp, Waterfox) with
optimal settings for Zapret DPI bypass:
  - Disables browser proxy (direct connection via NFQUEUE)
  - Enables DNS-over-HTTPS via Cloudflare (bypasses TSPPU port 53 DNS poisoning)
  - Enables Encrypted Client Hello (ECH)
  - Disables HTTP/3 (QUIC) to prevent video buffering issues

Options:
  --dry-run   Show detected profiles without writing changes
  --revert    Remove Zapret configuration from browser profiles
  -h, --help  Show this help message
USAGE
}

while (($#)); do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --revert) REVERT=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
    PYTHON="python3"
fi

PYTHONPATH="${PROJECT_ROOT}/src" "$PYTHON" -c '
import sys
from zapret_hub.services.browser_config import (
    discover_gecko_profiles,
    setup_all_gecko_browsers,
)

dry_run = int(sys.argv[1])
revert = int(sys.argv[2])

profiles = discover_gecko_profiles()
if not profiles:
    print("No Gecko browser profiles found in standard directories.")
    sys.exit(0)

if dry_run:
    print(f"Found {len(profiles)} browser profile(s):")
    for p in profiles:
        print("  - " + str(p / "user.js"))
    print("\nRun without --dry-run to apply settings.")
    sys.exit(0)

modified = setup_all_gecko_browsers(revert=bool(revert))
action = "Reverted" if revert else "Configured"
for path in modified:
    print(f"{action} Zapret DoH settings in: {path}")

print(f"\nSuccessfully {action.lower()} {len(modified)} browser profile(s).")
if not revert:
    print("Please restart your browser to apply changes.")
' "$DRY_RUN" "$REVERT"
