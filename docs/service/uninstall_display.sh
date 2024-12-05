#!/bin/bash

echo "----------------------------------------"
echo "Display Programme Uninstall Script"
echo "Version: 0.0.1 (2024-12-05)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024 Bence Damokos"
echo "----------------------------------------"

BACKUP_DIR="/opt/display_setup_backup"
BACKUP_MANIFEST="$BACKUP_DIR/manifest.txt"

# ... rest of the script ...

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