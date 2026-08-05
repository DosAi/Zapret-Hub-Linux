# scripts/lib/distro.sh
#
# Distribution and package-manager abstraction for the Zapret Hub Linux
# installer. POSIX sh only; safe to source from both /bin/sh and bash.
#
# Supported families:
#   debian  - Debian, Ubuntu and derivatives (apt-get)
#   rhel    - Fedora, RHEL, CentOS and derivatives (dnf/yum)
#   suse    - openSUSE and SUSE Enterprise (zypper)
#   arch    - Arch Linux and derivatives (pacman)
#   alpine  - Alpine Linux (apk)
#
# Override the os-release source with ZH_OS_RELEASE (path to a file) to test
# family detection without touching /etc/os-release.
#
# Immutable, image-based Fedora derivatives (Silverblue/Kinoite, Bazzite,
# Universal Blue, ...) are detected via /run/ostree-booted and use rpm-ostree
# instead of dnf. Pin that detection with ZH_ATOMIC=1 in non-atomic CI.
#
# For a non-atomic rhel family, pin the manager with ZH_RHEL_MANAGER=dnf|yum;
# useful in environments (such as CI) that do not have dnf installed.

if [ "${ZH_DISTRO_LOADED:-}" = "1" ]; then
    return 0 2>/dev/null || true
fi
ZH_DISTRO_LOADED=1

_ZH_OS_RELEASE=${ZH_OS_RELEASE:-/etc/os-release}

_zh_load_os_release() {
    [ -r "$_ZH_OS_RELEASE" ] && . "$_ZH_OS_RELEASE"
}

# Echo one of: debian, rhel, suse, arch, alpine, unknown
zh_distro_family() {
    _zh_load_os_release
    case "${ID:-}" in
        debian|ubuntu|kali|linuxmint|mint|pop|elementary|raspbian|mx|zorin|devuan|deepin|tuxedo|tails)
            echo debian
            return 0
            ;;
        fedora|rhel|centos|rocky|almalinux|ol|amzn|scientific|eurolinux|nobara|mageia|bazzite)
            echo rhel
            return 0
            ;;
        arch|manjaro|endeavouros|arcolinux|cachyos|garuda|artix|archcraft|rebornos)
            echo arch
            return 0
            ;;
        opensuse-leap|opensuse-tumbleweed|opensuse-leap-micro|sled|sles)
            echo suse
            return 0
            ;;
        alpine)
            echo alpine
            return 0
            ;;
    esac
    case " ${ID_LIKE:-} " in
        *" debian "*|*" ubuntu "*) echo debian ;;
        *" rhel "*|*" fedora "*) echo rhel ;;
        *" arch "*) echo arch ;;
        *" suse "*|*" opensuse "*|*" sles "*) echo suse ;;
        *" alpine "*) echo alpine ;;
        *) echo unknown ;;
    esac
}

# Human readable OS name for messages.
zh_os_name() {
    _zh_load_os_release
    echo "${PRETTY_NAME:-${NAME:-${ID:-unknown}}}"
}

# True (0) if the running system is immutable and image-based (rpm-ostree):
# Fedora Atomic/Silverblue/Kinoite, Bazzite, Universal Blue and other ostree
# images. Such systems cannot use dnf/yum against the live root and must layer
# packages with rpm-ostree instead. ZH_ATOMIC=1 forces atomic detection and
# ZH_ATOMIC=0 forces the non-atomic dnf/yum path (both useful for CI).
zh_is_atomic() {
    case "${ZH_ATOMIC:-}" in
        1) return 0 ;;
        0) return 1 ;;
    esac
    [ -f /run/ostree-booted ] && command -v rpm-ostree >/dev/null 2>&1
}

# Echo "rpm-ostree" for the atomic rhel family, otherwise "dnf" or "yum".
# ZH_RHEL_MANAGER pins the dnf/yum choice in environments where neither tool
# is installed (e.g. CI).
_zh_rhel_manager() {
    if zh_is_atomic; then
        echo rpm-ostree
        return 0
    fi
    case "${ZH_RHEL_MANAGER:-}" in
        dnf) echo dnf ;;
        yum) echo yum ;;
        *)
            if command -v dnf >/dev/null 2>&1; then
                echo dnf
            else
                echo yum
            fi
            ;;
    esac
}

# Echo the primary package manager command for the current family.
zh_pkg_manager() {
    case "$(zh_distro_family)" in
        debian) echo apt-get ;;
        rhel) _zh_rhel_manager ;;
        suse) echo zypper ;;
        arch) echo pacman ;;
        alpine) echo apk ;;
        *) echo unknown ;;
    esac
}

# Print the packages already requested (layered) in the booted rpm-ostree
# deployment, one per line. rpm-ostree aborts with "Package ... is already
# requested" when a previously layered package is requested again, which is
# exactly what the second (post-reboot) installer run does on immutable
# Fedora derivatives.
_zh_atomic_requested() {
    rpm-ostree status --json 2>/dev/null | awk '
        /"requested-packages" : \[/ { capture = 1; next }
        capture && /^      \],?$/ { exit }
        capture && /^        ".*/ {
            line = $0
            sub(/^[[:space:]]*"/, "", line)
            sub(/",?[[:space:]]*$/, "", line)
            print line
        }
    '
}

# Print the locally requested (locally layered) packages of the booted
# rpm-ostree deployment, one per line. These are versioned entries such as
# happ-3.3.6-301.x86_64.
_zh_atomic_requested_local() {
    rpm-ostree status --json 2>/dev/null | awk '
        /"requested-local-packages" : \[/ { capture = 1; next }
        capture && /^      \],?$/ { exit }
        capture && /^        ".*/ {
            line = $0
            sub(/^[[:space:]]*"/, "", line)
            sub(/",?[[:space:]]*$/, "", line)
            print line
        }
    '
}

# Echo the subset of "$@" that is not already requested in the booted
# rpm-ostree deployment, space separated. Intentionally leaves the request
# list untouched so that the post-reboot run of the installer layers nothing.
_zh_atomic_remaining() {
    requested=$(_zh_atomic_requested || true)
    remaining=
    for pkg in "$@"; do
        if printf '%s\n' "$requested" | grep -Fxq -- "$pkg"; then
            continue
        fi
        remaining="$remaining $pkg"
    done
    printf '%s\n' "$remaining"
}

# Refresh the package index. Run as root.
zh_pkg_update() {
    case "$(zh_distro_family)" in
        debian) apt-get update ;;
        rhel)
            if zh_is_atomic; then
                rpm-ostree refresh-md
            else
                $(_zh_rhel_manager) makecache
            fi
            ;;
        suse) zypper --non-interactive refresh ;;
        arch) pacman -Sy ;;
        alpine) apk update ;;
        *) return 1 ;;
    esac
}

# Install packages from the distribution repositories. Run as root.
zh_pkg_install() {
    case "$(zh_distro_family)" in
        debian) apt-get install -y "$@" ;;
        rhel)
            if zh_is_atomic; then
                remaining=$(_zh_atomic_remaining "$@")
                if [ -n "$remaining" ]; then
                    # shellcheck disable=SC2086
                    rpm-ostree install $remaining
                fi
            else
                $(_zh_rhel_manager) install -y "$@"
            fi
            ;;
        suse) zypper --non-interactive install "$@" ;;
        arch) pacman -S --noconfirm --needed "$@" ;;
        alpine) apk add --no-cache "$@" ;;
        *) return 1 ;;
    esac
}

# Install a local package file (native format for the current family).
# Alpine has no supported native Happ package.
zh_pkg_install_local() {
    pkg_file=$1
    [ -f "$pkg_file" ] || { echo "Package file not found: $pkg_file" >&2; return 1; }
    case "$(zh_distro_family)" in
        debian) apt-get install -y "$pkg_file" ;;
        rhel)
            if zh_is_atomic; then
                name=$(rpm -qp --qf '%{NAME}' "$pkg_file" 2>/dev/null || true)
                if [ -n "$name" ] && zh_pkg_installed "$name"; then
                    echo "Package $name is already layered and active; skipping $pkg_file."
                elif [ -n "$name" ] && _zh_atomic_requested_local | grep -Fq -- "$name-"; then
                    echo "Package $name is already requested for the next boot; skipping $pkg_file."
                else
                    rpm-ostree install "$pkg_file"
                fi
            else
                $(_zh_rhel_manager) install -y "$pkg_file"
            fi
            ;;
        suse) zypper --non-interactive install "$pkg_file" ;;
        arch) pacman -U --noconfirm "$pkg_file" ;;
        *) return 1 ;;
    esac
}

# Echo the exact install command (without executing it) for the current
# family. Used for dry-run previews so the preview matches what a real run
# executes on the same machine.
zh_pkg_install_cmd() {
    case "$(zh_distro_family)" in
        debian) echo "apt-get install -y $*" ;;
        rhel)
            if zh_is_atomic; then
                remaining=$(_zh_atomic_remaining "$@")
                if [ -n "$remaining" ]; then
                    echo "rpm-ostree install$remaining"
                else
                    echo "rpm-ostree (all requested packages already layered)"
                fi
            else
                echo "$(_zh_rhel_manager) install -y $*"
            fi
            ;;
        suse) echo "zypper --non-interactive install $*" ;;
        arch) echo "pacman -S --noconfirm --needed $*" ;;
        alpine) echo "apk add --no-cache $*" ;;
        *) echo unknown ;;
    esac
}

# True (0) if the package is installed, false (1) otherwise.
zh_pkg_installed() {
    pkg=$1
    case "$(zh_distro_family)" in
        debian) dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q 'install ok installed' ;;
        rhel|suse) rpm -q "$pkg" >/dev/null 2>&1 ;;
        arch) pacman -Q "$pkg" >/dev/null 2>&1 ;;
        alpine) apk info -e "$pkg" >/dev/null 2>&1 ;;
        *) return 1 ;;
    esac
}

# Echo the installed version of a package (empty when not installed).
zh_pkg_version() {
    pkg=$1
    case "$(zh_distro_family)" in
        debian) dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || true ;;
        rhel|suse) rpm -q --qf '%{VERSION}-%{RELEASE}' "$pkg" 2>/dev/null || true ;;
        arch) pacman -Q "$pkg" 2>/dev/null | awk '{print $2}' || true ;;
        *) true ;;
    esac
}

# Base dependency packages for the detected family, space separated.
zh_deps() {
    case "$(zh_distro_family)" in
        debian)
            # Current Kali and Debian split the former policykit-1 metapackage
            # into the daemon and the authorization helper.
            echo "python3 python3-venv python3-pip nodejs npm polkitd pkexec nftables iproute2 ca-certificates desktop-file-utils curl git tar gzip"
            ;;
        rhel)
            echo "python3 python3-virtualenv python3-pip nodejs npm polkit nftables iproute ca-certificates desktop-file-utils curl git tar gzip"
            ;;
        suse)
            echo "python3 python3-virtualenv python3-pip nodejs-default npm polkit nftables iproute2 ca-certificates desktop-file-utils curl git tar gzip"
            ;;
        arch)
            echo "python python-pip nodejs npm polkit nftables iproute2 ca-certificates desktop-file-utils curl git tar gzip"
            ;;
        alpine)
            echo ""
            ;;
        *)
            echo ""
            ;;
    esac
}

# True (0) if systemd is available, false (1) otherwise.
zh_is_systemd() {
    command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]
}

# Unified CPU architecture: x86_64, aarch64, i386 or armv7l.
zh_arch() {
    machine=$(uname -m 2>/dev/null || true)
    case "$machine" in
        x86_64|amd64) echo x86_64 ;;
        aarch64|arm64) echo aarch64 ;;
        i386|i486|i586|i686) echo i386 ;;
        armv6l|armv7l|armv8l|armhf) echo armv7l ;;
        *) echo "${machine:-unknown}" ;;
    esac
}
