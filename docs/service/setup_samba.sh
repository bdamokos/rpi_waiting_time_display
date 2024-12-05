#!/bin/bash

echo "----------------------------------------"
echo "Samba Setup Script"
echo "Version: 0.0.1 (2024-12-05)"  # AUTO-INCREMENT
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

# Add share configuration
cat >> /etc/samba/smb.conf << EOL

[${ACTUAL_USER}_home]
   comment = ${ACTUAL_USER}'s Home Directory
   path = ${ACTUAL_HOME}
   browseable = yes
   read only = no
   create mask = 0644
   directory mask = 0755
   valid users = ${ACTUAL_USER}
EOL

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
echo "\\\\$(hostname).local\\${ACTUAL_USER}_home"
echo ""
echo "Or on macOS/Linux:"
echo "smb://$(hostname).local/${ACTUAL_USER}_home"
echo ""
echo "Username: $ACTUAL_USER"
echo "Password: (the one you just set)"
echo "----------------------------------------"