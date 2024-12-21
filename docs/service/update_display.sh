#!/bin/bash

echo "----------------------------------------"
echo "Display Programme Update Script"
echo "Version: 0.0.2 (2024-12-21)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024 Bence Damokos"
echo "----------------------------------------"

# Check if script is run as root
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
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

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

# Function to check and update service dependencies
update_service_dependencies() {
    local service_file="$1"
    local dependency="$2"
    
    if [ -f "$service_file" ]; then
        if ! grep -q "After=.*$dependency" "$service_file"; then
            sed -i "/^After=/ s/$/ $dependency/" "$service_file"
            echo "Added $dependency to After= in $service_file"
        fi
        if ! grep -q "Wants=.*$dependency" "$service_file"; then
            sed -i "/^Wants=/ s/$/ $dependency/" "$service_file"
            echo "Added $dependency to Wants= in $service_file"
        fi
    fi
}

# Function to check and install package
check_package() {
    local package="$1"
    if ! dpkg -l | grep -q "^ii  $package "; then
        echo "Installing $package..."
        apt-get install -y "$package"
    fi
}

# Function to check and create directory
check_directory() {
    local dir="$1"
    local owner="$2"
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        chown "$owner:$owner" "$dir"
        echo "Created directory: $dir"
    fi
}

# Check for required packages
echo "Checking required packages..."
if confirm "Would you like to check and install required packages?"; then
    REQUIRED_PACKAGES=(
        "git"
        "gh"
        "fonts-dejavu"
        "watchdog"
        "python3-dev"
        "network-manager"
        "bluetooth"
        "bluez"
        "bluez-tools"
        "dnsmasq"
    )
    
    for package in "${REQUIRED_PACKAGES[@]}"; do
        check_package "$package"
    done
fi

# Check SPI interface
if confirm "Would you like to check and configure SPI interface?"; then
    if ! grep -q "^dtparam=spi=on" /boot/firmware/config.txt; then
        echo "SPI interface not enabled. Enabling..."
        raspi-config nonint do_spi 0
        echo "SPI interface enabled"
    else
        echo "SPI interface already enabled"
    fi
fi

# Check watchdog configuration
if confirm "Would you like to check and configure watchdog?"; then
    if ! grep -q "dtparam=watchdog=on" /boot/firmware/config.txt; then
        echo "Watchdog not enabled in config.txt. Enabling..."
        echo "dtparam=watchdog=on" >> /boot/firmware/config.txt
    fi
    
    if [ ! -f "/etc/watchdog.conf" ] || ! grep -q "watchdog-device = /dev/watchdog" "/etc/watchdog.conf"; then
        echo "Configuring watchdog..."
        cat > /etc/watchdog.conf << EOL
watchdog-device = /dev/watchdog
watchdog-timeout = 15
interval = 10
max-load-1 = 3.0
max-load-5 = 2.8
EOL
    else
        echo "Watchdog already configured"
    fi
fi

# Check virtual environment
if confirm "Would you like to check and configure Python virtual environment?"; then
    if [ ! -d "$ACTUAL_HOME/display_env" ]; then
        echo "Virtual environment missing. Creating..."
        su - "$ACTUAL_USER" -c "python3 -m venv $ACTUAL_HOME/display_env"
        su - "$ACTUAL_USER" -c "source $ACTUAL_HOME/display_env/bin/activate && cd $ACTUAL_HOME/display_programme && pip install -r requirements.txt"
    else
        echo "Virtual environment already exists"
        if confirm "Would you like to update pip packages?"; then
            su - "$ACTUAL_USER" -c "source $ACTUAL_HOME/display_env/bin/activate && cd $ACTUAL_HOME/display_programme && pip install -r requirements.txt"
        fi
    fi
fi

# Check Waveshare drivers
if confirm "Would you like to check and install Waveshare drivers?"; then
    PYTHON_VERSION=$(su - $ACTUAL_USER -c "source $ACTUAL_HOME/display_env/bin/activate && python3 -c 'import sys; print(\".\"
    .join(map(str, sys.version_info[:2])))'")
    SITE_PACKAGES="$ACTUAL_HOME/display_env/lib/python$PYTHON_VERSION/site-packages/waveshare_epd"
    
    if [ ! -d "$SITE_PACKAGES" ]; then
        echo "Installing Waveshare drivers..."
        mkdir -p "$SITE_PACKAGES"
        curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epd2in13g.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g.py
        curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epd2in13g_V2.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g_V2.py
        curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epdconfig.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epdconfig.py
    else
        echo "Waveshare drivers already installed"
        if confirm "Would you like to update the drivers?"; then
            curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epd2in13g.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g.py
            curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epd2in13g_V2.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g_V2.py
            curl -H "Cache-Control: no-cache" -o "$SITE_PACKAGES/epdconfig.py" https://raw.githubusercontent.com/waveshareteam/e-Paper/master/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epdconfig.py
        fi
    fi
fi

# Check WebSerial configuration
if confirm "Would you like to check and configure WebSerial service?"; then
    if [ -f "/etc/systemd/system/webserial.service" ]; then
        echo "Checking WebSerial service configuration..."
        update_service_dependencies "/etc/systemd/system/webserial.service" "bluetooth.target"
    else
        echo "WebSerial service not installed"
        if confirm "Would you like to install WebSerial support?"; then
            bash "$ACTUAL_HOME/display_programme/docs/service/setup_webserial.sh"
        fi
    fi
fi

# Check Bluetooth configuration
if confirm "Would you like to check and configure Bluetooth?"; then
    if [ -f "/etc/bluetooth/main.conf" ]; then
        if ! grep -q "^Name = EPaperDisplay" "/etc/bluetooth/main.conf"; then
            echo "Updating Bluetooth configuration..."
            cat > /etc/bluetooth/main.conf << EOL
[General]
Name = EPaperDisplay
Class = 0x000100
DiscoverableTimeout = 0
PairableTimeout = 0
EOL
            systemctl restart bluetooth
        else
            echo "Bluetooth already configured"
        fi
    else
        echo "Bluetooth configuration file not found"
        if confirm "Would you like to install Bluetooth support?"; then
            bash "$ACTUAL_HOME/display_programme/docs/service/setup_bluetooth_serial.sh"
        fi
    fi
fi

# Check network permissions
if confirm "Would you like to check and configure network permissions?"; then
    if ! groups $ACTUAL_USER | grep -q "\bnetdev\b"; then
        echo "Adding user to netdev group..."
        usermod -a -G netdev $ACTUAL_USER
    else
        echo "User already in netdev group"
    fi
    
    # Check PolicyKit configuration
    POLKIT_FILE="/etc/polkit-1/localauthority/50-local.d/10-network-manager.pkla"
    if [ ! -f "$POLKIT_FILE" ]; then
        echo "Creating PolicyKit configuration..."
        cat > "$POLKIT_FILE" << EOF
[Let users in netdev group modify NetworkManager]
Identity=unix-group:netdev
Action=org.freedesktop.NetworkManager.*
ResultAny=yes
ResultInactive=no
ResultActive=yes
EOF
    else
        echo "PolicyKit configuration already exists"
    fi
fi

# Check Noto font
if confirm "Would you like to check and install Noto font?"; then
    if [ ! -f "/usr/local/share/fonts/noto/NotoEmoji-Regular.ttf" ]; then
        echo "Installing Noto Emoji font..."
        mkdir -p /usr/local/share/fonts/noto
        wget -O NotoEmoji-Regular.ttf "https://github.com/google/fonts/raw/414e7e29b4a2a96d24ed12ac33df156823c6c262/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf"
        mv NotoEmoji-Regular.ttf /usr/local/share/fonts/noto/
        chmod 644 /usr/local/share/fonts/noto/NotoEmoji-Regular.ttf
        fc-cache -f
    else
        echo "Noto Emoji font already installed"
    fi
fi

# Restart services if needed
if confirm "Would you like to restart services?"; then
    systemctl daemon-reload
    systemctl enable watchdog
    systemctl start watchdog
    systemctl enable display.service
    systemctl restart display.service
    
    if [ -f "/etc/systemd/system/webserial.service" ]; then
        systemctl enable webserial.service
        systemctl restart webserial.service
    fi
fi

echo "----------------------------------------"
echo "Update completed!"
echo "You may need to restart your Raspberry Pi for some changes to take effect."
if confirm "Would you like to restart now?"; then
    reboot
fi 