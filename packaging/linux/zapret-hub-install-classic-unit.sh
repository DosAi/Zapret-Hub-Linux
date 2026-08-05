#!/bin/sh
# Narrow pkexec helper for Zapret Hub: (re)create the classic Zapret systemd
# unit when the Power button finds it missing. Installed as /usr/local/sbin
# and owned by root, so users cannot modify it to escalate privileges.
#
# It only writes the unit file and runs `systemctl daemon-reload`. It never
# starts, stops, restarts, enables, or disables the service.
#
# Usage: zapret-hub-install-classic-unit <classic-root>
set -eu

# The helper is installed root-owned but reachable through pkexec; refuse to
# run from any other context so a compromised user session cannot abuse it.
[ "$(id -u)" -eq 0 ] || { echo "must run as root (via pkexec)" >&2; exit 2; }

CLASSIC_ROOT=$1

# Defense in depth: only known managed install roots may be written into a
# system unit. polkit approval is not enough; reject everything else here.
case "$CLASSIC_ROOT" in
    /opt/zapret-discord-youtube-linux) ;;
    /opt/zapret-hub/zapret-discord-youtube-linux) ;;
    /opt/zapret-discord-youtube) ;;
    /home/*/zapret-discord-youtube-linux) ;;
    /home/*/Apps/zapret-discord-youtube-linux) ;;
    /var/home/*/zapret-discord-youtube-linux) ;;
    /var/home/*/Apps/zapret-discord-youtube-linux) ;;
    *)
        echo "unexpected classic root: $CLASSIC_ROOT" >&2
        exit 2
        ;;
esac

# The root must actually be a classic Zapret installation.
[ -x "$CLASSIC_ROOT/service.sh" ] || { echo "service.sh is missing in $CLASSIC_ROOT" >&2; exit 2; }
[ -x "$CLASSIC_ROOT/nfqws" ] || { echo "nfqws is missing in $CLASSIC_ROOT" >&2; exit 2; }
[ -d "$CLASSIC_ROOT/zapret-latest" ] || { echo "zapret-latest is missing in $CLASSIC_ROOT" >&2; exit 2; }

UNIT=/etc/systemd/system/zapret_discord_youtube.service
cat > "$UNIT" <<EOF
[Unit]
Description=Zapret Discord YouTube Linux (managed by Zapret Hub)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$CLASSIC_ROOT
ExecStart=/usr/bin/env bash $CLASSIC_ROOT/service.sh daemon
ExecStop=/usr/bin/env bash $CLASSIC_ROOT/service.sh kill
Restart=on-failure
RestartSec=3
TimeoutStopSec=30
KillMode=mixed

[Install]
WantedBy=multi-user.target
EOF
chmod 0644 "$UNIT"
systemctl daemon-reload
