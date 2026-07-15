#!/bin/sh
set -eu

SERVICE_NAME=display-client.service
PURGE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --service)
            if [ "$#" -lt 2 ]; then
                echo "Missing value for --service" >&2
                exit 2
            fi
            SERVICE_NAME=$2
            shift 2
            ;;
        --purge) PURGE=true; shift ;;
        -h|--help)
            echo "Usage: sudo $0 [--service NAME.service] [--purge]"
            exit 0
            ;;
        *) exit 2 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this uninstaller with sudo." >&2
    exit 1
fi

if ! printf '%s\n' "$SERVICE_NAME" | grep -Eq '^[A-Za-z0-9_.@:-]+\.service$'; then
    echo "Unsafe service name: $SERVICE_NAME" >&2
    exit 2
fi

systemctl disable --now display-watchdog.timer 2>/dev/null || true
rm -f /etc/systemd/system/display-watchdog.timer
rm -f /etc/systemd/system/display-watchdog.service
rm -f "/etc/systemd/system/$SERVICE_NAME.d/20-display-health.conf"
rmdir "/etc/systemd/system/$SERVICE_NAME.d" 2>/dev/null || true
rm -rf /usr/local/lib/display-watchdog

if [ "$PURGE" = true ]; then
    rm -rf /etc/display-watchdog /var/lib/display-watchdog
else
    echo "Preserved /etc/display-watchdog and /var/lib/display-watchdog for rollback/audit."
fi

systemctl daemon-reload
systemctl reset-failed display-watchdog.service 2>/dev/null || true
echo "Removed the display watchdog.  The display service was not restarted."
