#!/usr/bin/env bash
set -euo pipefail

EXPECTED_FAMILY=${1:?usage: distro_smoke.sh FAMILY PACKAGE_MANAGER [supported|unsupported]}
EXPECTED_MANAGER=${2:?usage: distro_smoke.sh FAMILY PACKAGE_MANAGER [supported|unsupported]}
EXPECTED_STATUS=${3:-supported}
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)

# shellcheck disable=SC1091
. "$PROJECT_ROOT/scripts/lib/distro.sh"

actual_family=$(zh_distro_family)
actual_manager=$(zh_pkg_manager)
[[ "$actual_family" == "$EXPECTED_FAMILY" ]]
[[ "$actual_manager" == "$EXPECTED_MANAGER" ]]

if [[ "$EXPECTED_STATUS" == "unsupported" ]]; then
    if "$PROJECT_ROOT/install.sh" --dry-run --no-launch >/tmp/zapret-hub-smoke.out 2>/tmp/zapret-hub-smoke.err; then
        echo "The installer unexpectedly accepted unsupported family: $actual_family" >&2
        exit 1
    fi
    grep -q "not supported yet" /tmp/zapret-hub-smoke.err
    exit 0
fi

preview=$("$PROJECT_ROOT/install.sh" --dry-run --no-launch 2>&1)
grep -q "Package family: $EXPECTED_FAMILY" <<<"$preview"
grep -q "Package manager: $EXPECTED_MANAGER" <<<"$preview"
grep -q "install bundled Zapret2" <<<"$preview"
grep -q "install official Happ" <<<"$preview"

# Validate package names against the actual repositories of the container,
# without installing packages or touching services/network configuration.
read -r -a deps <<<"$(zh_deps)"
case "$actual_family" in
    debian)
        apt-get update -qq
        for package in "${deps[@]}"; do
            echo "Checking dependency: $package"
            apt-cache show "$package" >/dev/null
        done
        ;;
    rhel)
        for package in "${deps[@]}"; do
            echo "Checking dependency: $package"
            "$actual_manager" -q repoquery --whatprovides="$package" | grep -q .
        done
        ;;
    arch)
        pacman -Sy --noconfirm >/dev/null
        for package in "${deps[@]}"; do
            echo "Checking dependency: $package"
            pacman -Si "$package" >/dev/null
        done
        ;;
    suse)
        zypper --non-interactive refresh
        echo "Checking dependency transaction: ${deps[*]}"
        zypper --non-interactive --no-refresh install --dry-run --no-recommends "${deps[@]}"
        ;;
esac

echo "Validated $actual_family with $actual_manager (${#deps[@]} dependency names)."
