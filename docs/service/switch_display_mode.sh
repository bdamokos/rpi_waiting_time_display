#!/bin/bash

# Script to switch between Docker and normal versions of the display service
# To make it executable, run:
# chmod +x switch_display_mode.sh
# Usage: ./switch_display_mode.sh [docker|normal|remote]

echo "----------------------------------------"
echo "Switching display mode script"
echo "Version: 0.0.2 (2025-01-13)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024-2025 Bence Damokos"
echo "----------------------------------------"

# Constants
DISPLAY_PROGRAMME_PATH="$HOME/display_programme"
SERVICE_PATH="/etc/systemd/system/display.service"
SCRIPT_PATH="$HOME/start_display.sh"
ACTUAL_USER=$(whoami)
ACTUAL_HOME="$HOME"

# Function to show usage
show_usage() {
    echo "Usage: $0 [docker|normal|remote]"
    echo "Switches the display service between Docker, normal, and remote server mode"
    exit 1
}

# Function to stop service
stop_service() {
    echo "Stopping display service..."
    sudo systemctl stop display.service
}

# Function to switch to specified mode
switch_mode() {
    local mode=$1
    local service_source=""
    local script_source=""
    
    case "$mode" in
        docker)
            service_source="$DISPLAY_PROGRAMME_PATH/docs/service/display.service.docker.example"
            script_source="$DISPLAY_PROGRAMME_PATH/docs/service/start_display.sh.docker.example"
            echo "Switching to Docker mode..."
            ;;
        remote)
            service_source="$DISPLAY_PROGRAMME_PATH/docs/service/display.service.remote_server.example"
            script_source="$DISPLAY_PROGRAMME_PATH/docs/service/start_display.sh.remote_server.example"
            echo "Switching to remote server mode..."
            ;;
        *)
            service_source="$DISPLAY_PROGRAMME_PATH/docs/service/display.service.example"
            script_source="$DISPLAY_PROGRAMME_PATH/docs/service/start_display.sh.example"
            echo "Switching to normal mode..."
            ;;
    esac

    # Copy and modify service file
    echo "Updating service file..."
    sudo sed -e "s|User=pi|User=$ACTUAL_USER|g" \
        -e "s|/home/pi|$ACTUAL_HOME|g" \
        "$service_source" > "$SERVICE_PATH"
    
    # Copy and make executable the start script
    echo "Updating start script..."
    cp "$script_source" "$SCRIPT_PATH"
    chmod +x "$SCRIPT_PATH"
    
    # Reload systemd
    echo "Reloading systemd..."
    sudo systemctl daemon-reload
    
    # Restart service
    echo "Starting display service..."
    sudo systemctl restart display.service
    
    # Show status
    echo "Current status:"
    sudo systemctl status display.service --no-pager
}

# Main script
if [ "$#" -ne 1 ]; then
    show_usage
fi

case "$1" in
    docker|normal|remote)
        stop_service
        switch_mode "$1"
        ;;
    *)
        show_usage
        ;;
esac

echo "Switch completed. You can check the logs with: journalctl -u display.service -f" 