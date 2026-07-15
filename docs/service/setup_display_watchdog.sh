#!/bin/sh
set -eu

RECOVERY_ENABLED=false
SERVICE_NAME=display-client.service

usage() {
    echo "Usage: sudo $0 [--service NAME.service] [--enable-legacy-recovery]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --service)
            if [ "$#" -lt 2 ]; then
                usage >&2
                exit 2
            fi
            SERVICE_NAME=$2
            shift 2
            ;;
        --enable-legacy-recovery)
            RECOVERY_ENABLED=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

if ! printf '%s\n' "$SERVICE_NAME" | grep -Eq '^[A-Za-z0-9_.@:-]+\.service$'; then
    echo "Unsafe service name: $SERVICE_NAME" >&2
    exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
INSTALL_DIR=/usr/local/lib/display-watchdog
CONFIG_DIR=/etc/display-watchdog
DROP_IN_DIR="/etc/systemd/system/$SERVICE_NAME.d"

if ! systemctl cat "$SERVICE_NAME" >/dev/null 2>&1; then
    echo "Service is not installed: $SERVICE_NAME" >&2
    exit 1
fi

install -d -m 0755 "$INSTALL_DIR" "$CONFIG_DIR"
install -m 0755 "$REPO_DIR/display_watchdog.py" "$INSTALL_DIR/display_watchdog.py"
install -m 0644 "$SCRIPT_DIR/display-watchdog.service" /etc/systemd/system/display-watchdog.service
install -m 0644 "$SCRIPT_DIR/display-watchdog.timer" /etc/systemd/system/display-watchdog.timer
if [ "$SERVICE_NAME" != display-client.service ]; then
    install -d -m 0755 "$DROP_IN_DIR"
    install -m 0644 "$SCRIPT_DIR/display-watchdog-health.conf" "$DROP_IN_DIR/20-display-health.conf"
fi

if [ ! -e "$CONFIG_DIR/config.json" ]; then
    temporary_config=$(mktemp)
    trap 'rm -f "$temporary_config"' EXIT HUP INT TERM
    sed \
        -e "s|__SERVICE_NAME__|$SERVICE_NAME|g" \
        -e "s|__RECOVERY_ENABLED__|$RECOVERY_ENABLED|g" \
        "$SCRIPT_DIR/display-watchdog.config.json" > "$temporary_config"
    install -m 0640 "$temporary_config" "$CONFIG_DIR/config.json"
fi

/usr/bin/python3 "$INSTALL_DIR/display_watchdog.py" validate-config --config "$CONFIG_DIR/config.json"
systemctl daemon-reload
systemctl enable --now display-watchdog.timer

service_type=$(systemctl show "$SERVICE_NAME" --property=Type --value 2>/dev/null || true)
notify_access=$(systemctl show "$SERVICE_NAME" --property=NotifyAccess --value 2>/dev/null || true)
watchdog_usec=$(systemctl show "$SERVICE_NAME" --property=WatchdogUSec --value 2>/dev/null || true)

echo "Installed the watchdog auditor for $SERVICE_NAME."
echo "Recovery enabled: $RECOVERY_ENABLED"
echo "The display service was not restarted."
case "$watchdog_usec" in
    ""|0|0us|infinity) watchdog_active=false ;;
    *) watchdog_active=true ;;
esac
if [ "$service_type" = notify ] && [ "$notify_access" = main ] && [ "$watchdog_active" = true ]; then
    echo "Primary systemd notify watchdog detected."
else
    echo "Legacy service detected: audit signals work now; systemd notify becomes primary after the split-client unit is installed."
fi
