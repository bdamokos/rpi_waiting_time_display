#!/bin/bash

echo "----------------------------------------"
echo "Samba Setup Script"
echo "Version: 0.0.2 (2024-12-05)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024 Bence Damokos"
echo "----------------------------------------"

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Get actual username (not root)
ACTUAL_USER=$(who am i | awk '{print $1}')
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

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
echo "Setting up Samba password for $ACTUAL_USER"
echo "Please enter the password you want to use for Samba:"
smbpasswd -a $ACTUAL_USER

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
echo "Password: (the one you just set)"
echo "----------------------------------------"