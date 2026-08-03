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
# For the rhel family, pin the manager with ZH_RHEL_MANAGER=dnf|yum; useful in
# environments (such as CI) that do not have dnf installed.

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

# Echo "dnf" or "yum" for the rhel family. ZH_RHEL_MANAGER pins the choice in
# environments where neither tool is installed (e.g. CI).
_zh_rhel_manager() {
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

# Refresh the package index. Run as root.
zh_pkg_update() {
    case "$(zh_distro_family)" in
        debian) apt-get update ;;
        rhel) $(_zh_rhel_manager) makecache ;;
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
        rhel) $(_zh_rhel_manager) install -y "$@" ;;
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
        rhel) $(_zh_rhel_manager) install -y "$pkg_file" ;;
        suse) zypper --non-interactive install "$pkg_file" ;;
        arch) pacman -U --noconfirm "$pkg_file" ;;
        *) return 1 ;;
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
