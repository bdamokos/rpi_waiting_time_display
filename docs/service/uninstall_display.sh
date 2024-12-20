#!/bin/bash

echo "----------------------------------------"
echo "Display Programme Uninstall Script"
echo "Version: 0.0.1 (2024-12-05)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024 Bence Damokos"
echo "----------------------------------------"

# Stop and disable WebSerial service
systemctl stop webserial.service
systemctl disable webserial.service
rm -f /etc/systemd/system/webserial.service
systemctl daemon-reload

# Remove USB gadget configuration
if [ -d "/sys/kernel/config/usb_gadget/pi4" ]; then
    cd /sys/kernel/config/usb_gadget/pi4
    echo "" > UDC
    rm -f configs/c.1/acm.usb0
    rmdir configs/c.1/strings/0x409 2>/dev/null
    rmdir configs/c.1 2>/dev/null
    rmdir functions/acm.usb0 2>/dev/null
    rmdir strings/0x409 2>/dev/null
    cd ..
    rmdir pi4 2>/dev/null
fi

# Unload modules
modprobe -r usb_f_acm
modprobe -r libcomposite

BACKUP_DIR="/opt/display_setup_backup"
BACKUP_MANIFEST="$BACKUP_DIR/manifest.txt"

# OOPS something is missing here

# Check if backups exist
if [ ! -d "$BACKUP_DIR" ] || [ ! -f "$BACKUP_MANIFEST" ]; then
    echo "Warning: No backup files found. Some original files may not be restored."
    if ! confirm "Continue anyway?"; then
        echo "Uninstall cancelled."
        exit 1
    fi
fi

# Call cleanup function
cleanup

echo "Uninstall completed."