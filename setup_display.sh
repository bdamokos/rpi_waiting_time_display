#!/bin/bash

# Store backup information in a fixed location
BACKUP_DIR="/opt/display_setup_backup"
BACKUP_MANIFEST="$BACKUP_DIR/manifest.txt"
MODIFIED_FILES=()

# Function to create backup of a file
backup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        local backup_path="$BACKUP_DIR${file}"
        mkdir -p "$(dirname "$backup_path")"
        cp "$file" "$backup_path"
        MODIFIED_FILES+=("$file")
        echo "$file" >> "$BACKUP_MANIFEST"
        echo "Backed up: $file"
    fi
}

# Function to setup uninstall script
setup_uninstall() {
    echo "Setting up uninstall script..."
    su - $ACTUAL_USER -c "cp $ACTUAL_HOME/display_programme/docs/service/uninstall_display.sh $ACTUAL_HOME/uninstall_display.sh"
    su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/uninstall_display.sh"
    echo "Uninstall script created at: $ACTUAL_HOME/uninstall_display.sh"
}

# Function to restore backups and cleanup
cleanup() {
    echo "----------------------------------------"
    echo "Cleaning up installation..."
    
    # Stop and disable service
    systemctl stop display.service
    systemctl disable display.service
    rm -f /etc/systemd/system/display.service
    systemctl daemon-reload
    
    # Remove installed packages (optional)
    if confirm "Would you like to remove installed packages?"; then
        apt-get remove -y git gh fonts-dejavu watchdog python3-dev
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
    
    # Disable SPI interface
    if confirm "Disable SPI interface?"; then
        raspi-config nonint do_spi 1
    fi
    
    # Setup uninstall script before exiting
    setup_uninstall
    
    # Optionally remove backup directory
    if confirm "Remove backup files?"; then
        rm -rf "$BACKUP_DIR"
    fi
    
    echo "Cleanup completed."
    echo "----------------------------------------"
    echo "You can use the uninstall script later with: sudo ~/uninstall_display.sh"
    echo "----------------------------------------"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"
touch "$BACKUP_MANIFEST"

echo "----------------------------------------"
echo "Display Programme Setup Script"
echo "Version: 0.0.16 (2024-12-07)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024 Bence Damokos"
echo "----------------------------------------"

# Function to check if command succeeded
check_error() {
    if [ $? -ne 0 ]; then
        echo "----------------------------------------"
        echo "Error: $1"
        echo "----------------------------------------"
        if confirm "Would you like to continue despite this error? (Accept the risks)"; then
            echo "Continuing despite the error as per user request."
            echo "----------------------------------------"
        else
            echo "Setup failed."
            if confirm "Would you like to clean up and restore previous state?"; then
                cleanup
            fi
            exit 1
        fi
    fi
}

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

# Check if script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root (sudo)"
    exit 1
fi

# Get actual username (not root)
ACTUAL_USER=$(who am i | awk '{print $1}')
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

echo "Setting up for user: $ACTUAL_USER"
echo "Home directory: $ACTUAL_HOME"

# Enable SPI interface
echo "Enabling SPI interface..."
raspi-config nonint do_spi 0
check_error "Failed to enable SPI"

# Install required packages
echo "Installing required packages..."
apt-get update
check_error "Failed to update package list"

# Install dependencies
apt-get install -y git gh fonts-dejavu watchdog python3-dev nmcli
check_error "Failed to install packages"

# Setup watchdog
echo "Setting up watchdog..."
if ! grep -q "dtparam=watchdog=on" /boot/firmware/config.txt; then
    echo "dtparam=watchdog=on" >> /boot/firmware/config.txt
fi

cat > /etc/watchdog.conf << EOL
watchdog-device = /dev/watchdog
watchdog-timeout = 15
interval = 10
max-load-1 = 3.0
max-load-5 = 2.8
EOL

systemctl enable watchdog
systemctl start watchdog

# Switch to actual user for git operations
echo "Setting up git..."
su - $ACTUAL_USER -c "gh auth login"
check_error "Failed to login to GitHub"

# Clone repositories
echo "Cloning repositories..."
cd $ACTUAL_HOME
su - $ACTUAL_USER -c "gh repo clone bdamokos/rpi_waiting_time_display display_programme"
check_error "Failed to clone display programme"

su - $ACTUAL_USER -c "gh repo clone bdamokos/brussels_transit"
check_error "Failed to clone brussels transit"

# Setup virtual environment
echo "Setting up virtual environment..."
su - $ACTUAL_USER -c "python3 -m venv $ACTUAL_HOME/display_env"
check_error "Failed to create virtual environment"

# Install requirements
echo "Installing requirements..."
su - $ACTUAL_USER -c "source $ACTUAL_HOME/display_env/bin/activate && cd $ACTUAL_HOME/display_programme && pip install -r requirements.txt"
check_error "Failed to install display programme requirements"

su - $ACTUAL_USER -c "source $ACTUAL_HOME/display_env/bin/activate && cd $ACTUAL_HOME/brussels_transit && pip install -r requirements.txt"
check_error "Failed to install brussels transit requirements"

# Install Waveshare drivers
echo "Installing Waveshare e-Paper drivers..."
PYTHON_VERSION=$(su - $ACTUAL_USER -c "source $ACTUAL_HOME/display_env/bin/activate && python3 -c 'import sys; print(\".\"
.join(map(str, sys.version_info[:2])))'")
SITE_PACKAGES="$ACTUAL_HOME/display_env/lib/python$PYTHON_VERSION/site-packages/waveshare_epd"

mkdir -p "$SITE_PACKAGES"
curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epd2in13g.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g.py
curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epd2in13g_V2.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g_V2.py
curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epdconfig.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epdconfig.py
check_error "Failed to install Waveshare drivers"

# Setup service files
echo "Setting up service files..."
# Make service scripts executable
su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/display_programme/docs/service/setup_samba.sh"
su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/display_programme/docs/service/switch_display_mode.sh"
su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/display_programme/docs/service/uninstall_display.sh"

# Copy and modify service file
sed -e "s|User=pi|User=$ACTUAL_USER|g" \
    -e "s|/home/pi|$ACTUAL_HOME|g" \
    $ACTUAL_HOME/display_programme/docs/service/display.service.example > /etc/systemd/system/display.service
check_error "Failed to setup service file"

# Copy and setup scripts
su - $ACTUAL_USER -c "cp $ACTUAL_HOME/display_programme/docs/service/switch_display_mode.sh $ACTUAL_HOME/switch_display_mode.sh"
su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/switch_display_mode.sh"

# Ask user which mode they want to use
if confirm "Would you like to use Docker mode? (No for normal mode)"; then
    echo "Setting up Docker mode..."
    # Install Docker if not present
    if ! command -v docker &> /dev/null; then
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        usermod -aG docker $ACTUAL_USER
        check_error "Failed to install Docker"
    fi
    su - $ACTUAL_USER -c "cp $ACTUAL_HOME/display_programme/docs/service/start_display.sh.docker.example $ACTUAL_HOME/start_display.sh"
else
    echo "Setting up normal mode..."
    su - $ACTUAL_USER -c "cp $ACTUAL_HOME/display_programme/docs/service/start_display.sh.example $ACTUAL_HOME/start_display.sh"
fi

su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/start_display.sh"

# Create .env file
if [ ! -f "$ACTUAL_HOME/display_programme/.env" ]; then
    echo "Creating .env file..."
    su - $ACTUAL_USER -c "cp $ACTUAL_HOME/display_programme/.env.example $ACTUAL_HOME/display_programme/.env"
    echo "Please edit the .env file with your settings:"
    echo "nano $ACTUAL_HOME/display_programme/.env"
fi

setup_uninstall

# Ask about Samba setup
if confirm "Would you like to set up Samba file sharing? This will allow you to edit files from your computer"; then
    echo "Setting up Samba..."
    bash "$ACTUAL_HOME/display_programme/docs/service/setup_samba.sh"
    check_error "Failed to setup Samba"
fi

# Add to the existing setup script
echo "Setting up WiFi captive portal dependencies..."
if ! command -v dnsmasq &> /dev/null; then
    apt-get update
    apt-get install -y dnsmasq
else
    echo "dnsmasq already installed"
fi

# Enable IP forwarding if not already enabled
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    sysctl -p
else
    echo "IP forwarding already enabled"
fi

# Setup network permissions
echo "Setting up network permissions..."
if ! groups $ACTUAL_USER | grep -q "\bnetdev\b"; then
    usermod -a -G netdev $ACTUAL_USER
    echo "Added $ACTUAL_USER to netdev group"
else
    echo "User already in netdev group"
fi

POLKIT_FILE="/etc/polkit-1/localauthority/50-local.d/10-network-manager.pkla"
if [ ! -f "$POLKIT_FILE" ]; then
    cat > "$POLKIT_FILE" << EOF
[Let users in netdev group modify NetworkManager]
Identity=unix-group:netdev
Action=org.freedesktop.NetworkManager.*
ResultAny=yes
ResultInactive=no
ResultActive=yes
EOF
    echo "Created PolicyKit configuration"
else
    echo "PolicyKit configuration already exists"
fi
check_error "Failed to setup network permissions"

# Create a script that can be called with sudo
if [ ! -f "/usr/local/bin/wifi-portal-setup" ]; then
    cat > /usr/local/bin/wifi-portal-setup << 'EOL'
#!/bin/bash
# Configure dnsmasq with more options
cat > /etc/dnsmasq.conf << EOF
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
address=/#/192.168.4.1
dhcp-option=3,192.168.4.1  # Gateway
dhcp-option=6,192.168.4.1  # DNS
no-resolv
no-poll
no-hosts
server=8.8.8.8
server=8.8.4.4
log-queries
log-dhcp
EOF

# Configure network interface
ifconfig wlan0 192.168.4.1 netmask 255.255.255.0

# Configure iptables more thoroughly
iptables -t nat -F
iptables -F
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 80
iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 80
iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
iptables -A FORWARD -i wlan0 -o eth0 -j ACCEPT
iptables -A FORWARD -i eth0 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT

# Restart dnsmasq
systemctl restart dnsmasq
EOL
    chmod +x /usr/local/bin/wifi-portal-setup
    echo "Created wifi portal setup script"
else
    echo "Wifi portal setup script already exists"
fi

# Create or update sudoers entry
SUDOERS_FILE="/etc/sudoers.d/wifi-portal"
REQUIRED_ENTRIES=(
    "$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/local/bin/wifi-portal-setup"
    "$ACTUAL_USER ALL=(ALL) NOPASSWD: /sbin/iptables"
    "$ACTUAL_USER ALL=(ALL) NOPASSWD: /bin/systemctl"
    "$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/bin/nmcli"
)

# Create new sudoers content
echo "Setting up network permissions in sudoers..."
SUDOERS_CONTENT=""
for entry in "${REQUIRED_ENTRIES[@]}"; do
    SUDOERS_CONTENT+="$entry"$'\n'
done

# Safely update the sudoers file
echo "$SUDOERS_CONTENT" > "/tmp/wifi-portal"
visudo -c -f "/tmp/wifi-portal"
if [ $? -eq 0 ]; then
    mv "/tmp/wifi-portal" "$SUDOERS_FILE"
    chmod 440 "$SUDOERS_FILE"
    echo "Updated sudoers file successfully"
else
    rm -f "/tmp/wifi-portal"
    echo "Failed to create valid sudoers file"
    check_error "Invalid sudoers syntax"
fi

# Download noto font
echo "Downloading Noto font..."
#!/bin/bash

# Create system font directory if it doesn't exist
sudo mkdir -p /usr/local/share/fonts/noto

# Check if font already exists
if [ -f "/usr/local/share/fonts/noto/NotoEmoji-Regular.ttf" ]; then
    echo "Noto Emoji font already installed."
else
    echo "Downloading Noto Emoji font..."
    # Download the font
    wget -O NotoEmoji-Regular.ttf "https://github.com/google/fonts/raw/414e7e29b4a2a96d24ed12ac33df156823c6c262/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf"

    # Move it to the system fonts directory
    sudo mv NotoEmoji-Regular.ttf /usr/local/share/fonts/noto/

    # Set proper permissions
    sudo chmod 644 /usr/local/share/fonts/noto/NotoEmoji-Regular.ttf

    # Update font cache
    sudo fc-cache -f -v

    echo "Noto Emoji font installed successfully."
fi

# Verify installation
echo "Verifying Noto font installation..."
fc-list | grep -i noto

# Start the debug server
echo "Starting the debug server..."
su - $ACTUAL_USER -c "source $ACTUAL_HOME/display_env/bin/activate && python3 $ACTUAL_HOME/display_programme/debug_server.py &"
DEBUG_SERVER_PID=$!
check_error "Failed to start debug server"

# Wait for the debug server to exit
wait $DEBUG_SERVER_PID

echo "----------------------------------------"
echo "Setup completed!"
echo ""
echo "Next steps:"
echo "1. Edit your .env file by visiting: http://hostname:5002/debug/env" or manually by:
echo "   nano $ACTUAL_HOME/display_programme/.env"
echo "2. Once you are happy with your settings, press the 'I am happy with my initial settings, restart my Pi' button."
echo ""
echo "The Raspberry Pi will restart automatically in 10 seconds with the new settings."
echo ""
echo "To uninstall in the future, run: sudo ~/uninstall_display.sh"
echo "You will find this readme at: https://github.com/bdamokos/rpi_waiting_time_display"
echo "----------------------------------------"

# Enable and start service
systemctl daemon-reload
systemctl enable display.service
systemctl start display.service
# Restart the Raspberry Pi after a timeout
echo "Restarting Raspberry Pi in 10 seconds..."
sleep 10
reboot