#!/bin/sh
set -eu

usage() {
    echo "Usage: sudo $0 server|client [--activate]"
    echo "Stages a native split-role service; --activate switches services after staging."
}

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

role="${1:-}"
activate="${2:-}"
case "$role" in
    server|client) ;;
    *) usage; exit 2 ;;
esac
if [ -n "$activate" ] && [ "$activate" != "--activate" ]; then
    usage
    exit 2
fi

actual_user="${SUDO_USER:-$(logname)}"
actual_home="$(getent passwd "$actual_user" | cut -d: -f6)"
repository="$actual_home/display_programme"
if [ ! -d "$repository/.git" ]; then
    echo "Expected the checkout at $repository" >&2
    exit 1
fi

if [ ! -f "$repository/.env" ]; then
    install -o "$actual_user" -g "$actual_user" -m 0600 "$repository/.env.example" "$repository/.env"
    echo "Created $repository/.env; configure role URLs/tokens before activation."
fi
chmod 0600 "$repository/.env"

if [ "$role" = "server" ]; then
    venv="$actual_home/display_server_env"
    requirements="requirements.server.txt"
    example="display-render-server.service.example"
    service="display-render-server.service"
else
    venv="$actual_home/display_env"
    requirements="requirements.txt"
    example="display-client.service.example"
    service="display-client.service"
fi

if [ ! -x "$venv/bin/python" ]; then
    su - "$actual_user" -c "python3 -m venv '$venv'"
fi
su - "$actual_user" -c "'$venv/bin/pip' install --requirement '$repository/$requirements'"

temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
sed -e "s|User=pi|User=$actual_user|g" -e "s|/home/pi|$actual_home|g" \
    "$repository/docs/service/$example" > "$temporary"
install -m 0644 "$temporary" "/etc/systemd/system/$service"
systemctl daemon-reload

echo "Staged $service. Validate .env and run: sudo systemctl enable --now $service"
if [ "$activate" = "--activate" ]; then
    if [ "$role" = "client" ]; then
        systemctl disable --now display.service 2>/dev/null || true
    fi
    systemctl enable --now "$service"
    systemctl --no-pager --full status "$service"
fi
