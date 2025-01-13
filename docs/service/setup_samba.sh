#!/bin/bash

echo "----------------------------------------"
echo "Samba Setup Script"
echo "Version: 0.0.4 (2025-01-13)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024-2025 Bence Damokos"
echo "----------------------------------------"

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -p, --password     Samba password (for unattended mode)"
    echo "  -h, --help         Show this help message"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--password)
            if [ -n "$2" ] && [[ "$2" != -* ]]; then
                SAMBA_PASSWORD="$2"
                shift
            fi
            shift
            ;;
        -h|--help)
            show_usage
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            ;;
    esac
done

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Get actual username (not root)
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    ACTUAL_USER=$(logname)
fi
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

echo "Setting up Samba for user: $ACTUAL_USER"
echo "Home directory: $ACTUAL_HOME"

# Install Samba
echo "Installing Samba..."
apt-get update
apt-get install -y samba

# Backup original config
if [ ! -f /etc/samba/smb.conf.backup ]; then
    cp /etc/samba/smb.conf /etc/samba/smb.conf.backup
fi

# Create Samba password for user
if [ -n "$SAMBA_PASSWORD" ]; then
    echo "Setting up Samba password from command line..."
    (echo "$SAMBA_PASSWORD"; echo "$SAMBA_PASSWORD") | smbpasswd -a $ACTUAL_USER -s
else
    echo "Setting up Samba password for $ACTUAL_USER"
    echo "Please enter the password you want to use for Samba:"
    smbpasswd -a $ACTUAL_USER
fi

# Modify the [homes] section to allow write access
sed -i '/\[homes\]/,/^[^#[]/ s/read only = yes/read only = no/' /etc/samba/smb.conf
sed -i '/\[homes\]/,/^[^#[]/ s/create mask = 0700/create mask = 0644/' /etc/samba/smb.conf
sed -i '/\[homes\]/,/^[^#[]/ s/directory mask = 0700/directory mask = 0755/' /etc/samba/smb.conf

# Restart Samba
systemctl restart smbd
systemctl restart nmbd

# Configure firewall if it's active
if command -v ufw >/dev/null 2>&1; then
    echo "Configuring firewall..."
    ufw allow samba
fi

echo "----------------------------------------"
echo "Samba setup completed!"
echo ""
echo "You can now access your home directory at:"
echo "\\\\$(hostname).local\\$ACTUAL_USER"
echo ""
echo "Or on macOS/Linux:"
echo "smb://$(hostname).local/$ACTUAL_USER"
echo ""
echo "Username: $ACTUAL_USER"
if [ -n "$SAMBA_PASSWORD" ]; then
    echo "Password: (as provided)"
else
    echo "Password: (the one you just set)"
fi
echo "----------------------------------------"