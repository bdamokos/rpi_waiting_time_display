#!/bin/bash

echo "----------------------------------------"
echo "Display Programme Upgrade Script"
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2025 Bence Damokos"
echo "----------------------------------------"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Get actual username
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    ACTUAL_USER=$(logname)
fi

# Configuration
VERSION_FILE="/etc/display_programme/version"
VERSION_DIR="/etc/display_programme"

# Get version from setup_display.sh
SETUP_SCRIPT="$(dirname "$0")/setup_display.sh"
if [ ! -f "$SETUP_SCRIPT" ]; then
    SETUP_SCRIPT="$(dirname "$0")/../../setup_display.sh"
fi

if [ ! -f "$SETUP_SCRIPT" ]; then
    echo "Error: Could not find setup_display.sh"
    exit 1
fi

CURRENT_VERSION=$(grep "^echo \"Version: " "$SETUP_SCRIPT" | cut -d'"' -f2 | cut -d' ' -f2)
if [ -z "$CURRENT_VERSION" ]; then
    echo "Error: Could not determine version from setup_display.sh"
    exit 1
fi

# Create version directory if it doesn't exist
mkdir -p "$VERSION_DIR"

# Function to compare version numbers
version_gt() {
    test "$(printf '%s\n' "$@" | sort -V | head -n 1)" != "$1"
}

# Read the last executed version
if [ -f "$VERSION_FILE" ]; then
    LAST_VERSION=$(cat "$VERSION_FILE")
else
    LAST_VERSION="0.0.0"
fi

echo "Last executed version: $LAST_VERSION"
echo "Current version: $CURRENT_VERSION"

# Only proceed if current version is greater than last version
if ! version_gt "$CURRENT_VERSION" "$LAST_VERSION"; then
    echo "No upgrades needed."
    exit 0
fi

# Upgrade steps
echo "Performing upgrades..."

# Version 0.0.40 upgrades (first version with upgrade system)
if version_gt "0.0.40" "$LAST_VERSION"; then
    echo "Applying version 0.0.40 upgrades..."
    
    # Create log directories with correct permissions
    echo "Setting up log directories..."
    mkdir -p /var/log/display
    chown $ACTUAL_USER:$ACTUAL_USER /var/log/display
    chmod 755 /var/log/display
    
    # Create log files with correct permissions
    touch /var/log/display/display.out /var/log/display/display.err
    chown $ACTUAL_USER:$ACTUAL_USER /var/log/display/display.out /var/log/display/display.err
    chmod 644 /var/log/display/display.out /var/log/display/display.err
    
    # Create webserial log directory and files
    mkdir -p /var/log/webserial
    chown $ACTUAL_USER:$ACTUAL_USER /var/log/webserial
    chmod 755 /var/log/webserial
    
    touch /var/log/webserial/webserial.out /var/log/webserial/webserial.err
    chown $ACTUAL_USER:$ACTUAL_USER /var/log/webserial/webserial.out /var/log/webserial/webserial.err
    chmod 644 /var/log/webserial/webserial.out /var/log/webserial/webserial.err
    
    echo "Version 0.0.40 upgrades completed."
fi

# Add new version blocks here for future upgrades
# Example:
# if version_gt "0.0.41" "$LAST_VERSION"; then
#     echo "Applying version 0.0.41 upgrades..."
#     # Add upgrade steps here
# fi

# Update the version file
echo "$CURRENT_VERSION" > "$VERSION_FILE"
echo "Upgrade completed successfully." 