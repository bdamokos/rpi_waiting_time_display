#!/bin/bash

echo "----------------------------------------"
echo "Display Programme Uninstall Script"
echo "Version: 0.0.4 (2025-01-13)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024-2025 Bence Damokos"
echo "----------------------------------------"

# Function to prompt for yes/no
confirm() {
    read -p "$1 [y/N] " response
    case "$response" in
        [yY][eE][sS]|[yY]) 
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Get actual username
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    ACTUAL_USER=$(logname)
fi
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

# Store backup information in a fixed location
BACKUP_DIR="/opt/display_setup_backup"
BACKUP_MANIFEST="$BACKUP_DIR/manifest.txt"

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

# Function to restore backups and cleanup
cleanup() {
    echo "----------------------------------------"
    echo "Cleaning up installation..."
    
    # Stop and disable services
    systemctl stop display.service
    systemctl disable display.service
    systemctl stop watchdog
    systemctl disable watchdog
    systemctl stop bluetooth-serial.service
    systemctl disable bluetooth-serial.service
    rm -f /etc/systemd/system/display.service
    rm -f /etc/systemd/system/webserial.service
    rm -f /etc/systemd/system/bluetooth-serial.service
    systemctl daemon-reload
    
    # Remove watchdog configuration
    if [ -f "/boot/firmware/config.txt" ]; then
        sed -i '/dtparam=watchdog=on/d' /boot/firmware/config.txt
    fi
    rm -f /etc/watchdog.conf
    
    # Disable SPI interface
    raspi-config nonint do_spi 1
    
    # Remove installed packages
    if confirm "Would you like to remove installed packages?"; then
        apt-get remove -y git gh fonts-dejavu watchdog python3-dev network-manager dnsmasq libcairo2-dev pkg-config
    fi
    
    # Remove WiFi captive portal setup
    rm -f /usr/local/bin/wifi-portal-setup
    rm -f /etc/sudoers.d/wifi-portal
    
    # Remove network configurations
    if [ -f "/etc/sysctl.conf" ]; then
        sed -i '/net.ipv4.ip_forward=1/d' /etc/sysctl.conf
    fi
    rm -f /etc/polkit-1/localauthority/50-local.d/10-network-manager.pkla
    rm -f /etc/dnsmasq.conf
    
    # Remove Noto font
    if [ -f "/usr/local/share/fonts/noto/NotoEmoji-Regular.ttf" ]; then
        rm -f /usr/local/share/fonts/noto/NotoEmoji-Regular.ttf
        fc-cache -f
    fi
    
    # Remove virtual environment
    if [ -d "$ACTUAL_HOME/display_env" ]; then
        if confirm "Remove virtual environment?"; then
            rm -rf "$ACTUAL_HOME/display_env"
        fi
    fi
    
    # Remove cloned repositories with warning
    if [ -d "$ACTUAL_HOME/display_programme" ]; then
        echo "----------------------------------------"
        echo -e "\e[1;31mWARNING: Removing the display programme repository will delete all your settings,"
        echo -e "including your .env file and any customizations you've made!\e[0m"
        echo "----------------------------------------"
        if confirm "Are you ABSOLUTELY SURE you want to remove the display programme repository?"; then
            rm -rf "$ACTUAL_HOME/display_programme"
        fi
    fi
    if [ -d "$ACTUAL_HOME/brussels_transit" ]; then
        echo "----------------------------------------"
        echo -e "\e[1;31mWARNING: Removing the brussels transit repository will delete all your settings,"
        echo -e "including your .env file and any customizations you've made!\e[0m"
        echo "----------------------------------------"
        if confirm "Are you ABSOLUTELY SURE you want to remove the brussels transit repository?"; then
            rm -rf "$ACTUAL_HOME/brussels_transit"
        fi
    fi
    
    # Remove script files
    rm -f "$ACTUAL_HOME/start_display.sh"
    rm -f "$ACTUAL_HOME/switch_display_mode.sh"
    rm -f "$ACTUAL_HOME/uninstall_display.sh"
    rm -f "$ACTUAL_HOME/get-docker.sh"
    
    # Remove Docker if installed during setup
    if command -v docker &> /dev/null; then
        if confirm "Would you like to remove Docker?"; then
            apt-get remove -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            rm -rf /var/lib/docker
        fi
    fi
    
    # Remove Samba if it was installed
    if command -v smbd &> /dev/null; then
        if confirm "Would you like to remove Samba?"; then
            systemctl stop smbd
            systemctl disable smbd
            apt-get remove -y samba samba-common-bin
            rm -f /etc/samba/smb.conf
        fi
    fi
    
    # Restore backed up files
    if [ -f "$BACKUP_MANIFEST" ]; then
        echo "Restoring backed up files..."
        while IFS= read -r file; do
            if [ -f "$BACKUP_DIR$file" ]; then
                cp "$BACKUP_DIR$file" "$file"
                echo "Restored: $file"
            fi
        done < "$BACKUP_MANIFEST"
    fi
    
    # Optionally remove backup directory
    if confirm "Remove backup files?"; then
        rm -rf "$BACKUP_DIR"
    fi
    
    echo "Cleanup completed."
    echo "----------------------------------------"
    echo "System has been restored to its original state."
    echo "----------------------------------------"
    
    # Offer to restart
    if confirm "Would you like to restart your Raspberry Pi now?"; then
        echo "Restarting Raspberry Pi..."
        reboot
    else
        echo "Please restart your Raspberry Pi when convenient."
    fi
}

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