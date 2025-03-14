#!/bin/bash

echo "----------------------------------------"
echo "Display Programme Setup Script"
echo "Version: 0.0.42 (2025-01-24)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024-2025 Bence Damokos"
echo "----------------------------------------"

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -m, --mode         Setup mode (1=Normal, 2=Docker, 3=Remote) [default: 1]"
    echo "  -u, --update       Update mode (1=Releases, 2=Main, 3=None) [default: 1]"
    echo "  -s, --samba        Setup Samba (y/n) [default: n]"
    echo "  -p, --password     Samba password (required if samba=y)"
    echo "  -r, --restart      Auto restart after setup (y/n) [default: y]"
    echo "  -y, --unattended   Run in unattended mode with defaults"
    echo "  -h, --help         Show this help message"
    exit 1
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            if [ -n "$2" ]; then
                SETUP_MODE="$2"
                shift 2
            else
                echo "Error: --mode requires a value"
                show_usage
            fi
            ;;
        -u|--update)
            if [ -n "$2" ]; then
                UPDATE_MODE_CHOICE="$2"
                shift 2
            else
                echo "Error: --update requires a value"
                show_usage
            fi
            ;;
        -r|--restart)
            if [ -n "$2" ]; then
                AUTO_RESTART="$2"
                shift 2
            else
                echo "Error: --restart requires a value"
                show_usage
            fi
            ;;
        -y|--unattended)
            UNATTENDED=1
            shift
            ;;
        -h|--help)
            show_usage
            ;;
        -s|--samba|-p|--password)
            # Store these for processing at the end
            REMAINING_ARGS+=("$1")
            if [ -n "$2" ]; then
                REMAINING_ARGS+=("$2")
                shift
            fi
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            ;;
    esac
done

# Process Samba arguments at the end
for ((i=0; i<${#REMAINING_ARGS[@]}; i++)); do
    case ${REMAINING_ARGS[i]} in
        -s|--samba)
            if [ -n "${REMAINING_ARGS[i+1]}" ] && [[ "${REMAINING_ARGS[i+1]}" != -* ]]; then
                SETUP_SAMBA="${REMAINING_ARGS[i+1]}"
                ((i++))
            fi
            ;;
        -p|--password)
            if [ -n "${REMAINING_ARGS[i+1]}" ] && [[ "${REMAINING_ARGS[i+1]}" != -* ]]; then
                SAMBA_PASSWORD="${REMAINING_ARGS[i+1]}"
                ((i++))
            fi
            ;;
    esac
done

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
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

echo "Setting up for user: $ACTUAL_USER"
echo "Home directory: $ACTUAL_HOME"

# Function to prompt for yes/no with default
confirm() {
    local prompt="$1"
    local default="${2:-n}"  # Default to 'n' if not specified
    local default_upper=$(echo $default | tr '[:lower:]' '[:upper:]')
    local other=$(if [ "$default" = "y" ]; then echo "n"; else echo "y"; fi)
    local other_upper=$(echo $other | tr '[:lower:]' '[:upper:]')
    
    if [ -n "$UNATTENDED" ] && [ -n "$default" ]; then
        [ "$default" = "y" ]
        return
    fi
    
    read -p "$prompt [${default_upper}/${other}] " response
    case "$response" in
        [yY][eE][sS]|[yY]) 
            return 0
            ;;
        [nN][oO]|[nN])
            return 1
            ;;
        "")
            [ "$default" = "y" ]
            return
            ;;
        *)
            return 1
            ;;
    esac
}

if [ -z "$UNATTENDED" ]; then
    # Initial Configuration
    echo "----------------------------------------"
    echo "Initial Configuration"
    echo "----------------------------------------"

    # Setup mode selection if not provided
    if [ -z "$SETUP_MODE" ]; then
        echo "Please select setup mode:"
        echo "1) Normal mode (local backend)"
        echo "2) Docker mode (containerized backend)"
        echo "3) Remote server mode (external backend)"
        read -p "Enter your choice (1-3) [1]: " SETUP_MODE
    fi
    SETUP_MODE=${SETUP_MODE:-1}

    # Display type selection if not provided
    if [ -z "$DISPLAY_MODEL" ]; then
        echo "----------------------------------------"
        echo "Please select display type:"
        echo "# Display settings (If you don't know what to use, try: epd2in13g_V2 for 4-color displays, epd2in13_V4 for black and white displays)"
        read -p "Enter display type [epd2in13_V4]: " DISPLAY_MODEL
    fi
    DISPLAY_MODEL=${DISPLAY_MODEL:-"epd2in13_V4"}

    # Update mode selection if not provided
    if [ -z "$UPDATE_MODE_CHOICE" ]; then
        echo "----------------------------------------"
        echo "Please select update mode:"
        echo "1) Releases only (recommended, more stable)"
        echo "2) All updates (main branch, may be unstable)"
        echo "3) No updates (manual updates only)"
        read -p "Enter your choice (1-3) [1]: " UPDATE_MODE_CHOICE
    fi
    UPDATE_MODE_CHOICE=${UPDATE_MODE_CHOICE:-1}

    # Additional features if not provided
    if [ -z "$SETUP_SAMBA" ]; then
        echo "----------------------------------------"
        echo "Additional features:"
        if confirm "Would you like to set up Samba file sharing? This will allow you to edit files from your computer" "n"; then
            SETUP_SAMBA="yes"
            if [ -z "$SAMBA_PASSWORD" ]; then
                echo "Please enter the Samba password you would like to use:"
                read -s SAMBA_PASSWORD
                echo "Please confirm the Samba password:"
                read -s SAMBA_PASSWORD2
                if [ "$SAMBA_PASSWORD" != "$SAMBA_PASSWORD2" ]; then
                    echo "Passwords do not match. Samba setup will be disabled."
                    SETUP_SAMBA="no"
                    SAMBA_PASSWORD=""
                fi
            fi
        else
            SETUP_SAMBA="no"
        fi
    fi

    if [ -z "$AUTO_RESTART" ]; then
        if confirm "Would you like to restart automatically after setup?" "y"; then
            AUTO_RESTART="yes"
        else
            AUTO_RESTART="no"
        fi
    fi
else
    # Set defaults for unattended mode
    SETUP_MODE=${SETUP_MODE:-1}
    UPDATE_MODE_CHOICE=${UPDATE_MODE_CHOICE:-1}
    SETUP_SAMBA=${SETUP_SAMBA:-"no"}
    AUTO_RESTART=${AUTO_RESTART:-"yes"}
    DISPLAY_MODEL=${DISPLAY_MODEL:-"epd2in13_V4"}
    
    # In unattended mode, if Samba is enabled but no password provided, disable it
    if [ "$SETUP_SAMBA" = "yes" ] && [ -z "$SAMBA_PASSWORD" ]; then
        echo "Warning: Samba setup requested but no password provided in unattended mode."
        echo "Disabling Samba setup. Use -p or --password to provide a Samba password."
        SETUP_SAMBA="no"
    fi
fi

# Process update mode choice
case $UPDATE_MODE_CHOICE in
    2)
        UPDATE_MODE="main"
        echo "Selected: All updates (main branch)"
        ;;
    3)
        UPDATE_MODE="none"
        echo "Selected: No automatic updates"
        ;;
    *)
        UPDATE_MODE="releases"
        echo "Selected: Releases only"
        ;;
esac

echo "----------------------------------------"
echo "Configuration Summary:"
echo "Setup Mode: $SETUP_MODE"
echo "Update Mode: $UPDATE_MODE"
echo "Setup Samba: $SETUP_SAMBA"
echo "Auto Restart: $AUTO_RESTART"
echo "Display Type: $DISPLAY_MODEL"
echo "----------------------------------------"

if [ -z "$UNATTENDED" ]; then
    if ! confirm "Would you like to proceed with these settings?" "y"; then
        echo "Setup cancelled by user"
        exit 1
    fi
fi

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
    
    # Remove installed packages if selected
    if [ "$REMOVE_PACKAGES" = "yes" ]; then
        echo "Removing installed packages..."
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

    # Remove docker installer script if present
    rm -f "$ACTUAL_HOME/get-docker.sh"
    
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

# Function to clone a repository if it doesn't exist
clone_repository() {
    local repo_name="$1"
    local target_dir="$2"  # Optional parameter for target directory name
    local repo_path="$ACTUAL_HOME/$repo_name"
    
    # If target_dir is provided, use it instead of repo_name for the path
    if [ ! -z "$target_dir" ]; then
        repo_path="$ACTUAL_HOME/$target_dir"
    fi
    
    if [ ! -d "$repo_path" ]; then
        echo "Cloning $repo_name repository..."
        cd "$ACTUAL_HOME"
        su - "$ACTUAL_USER" -c "git clone https://github.com/bdamokos/$repo_name.git $target_dir"
        check_error "Failed to clone $repo_name"
    else
        echo "$repo_name repository already exists"
    fi
}

# Function to setup service files with correct user and paths
setup_service_files() {
    local mode="$1"
    local service_source=""
    local script_source=""
    
    case "$mode" in
        docker)
            service_source="display.service.docker.example"
            script_source="start_display.sh.docker.example"
            ;;
        remote)
            service_source="display.service.remote_server.example"
            script_source="start_display.sh.remote_server.example"
            ;;
        *)
            service_source="display.service.example"
            script_source="start_display.sh.example"
            ;;
    esac
    
    echo "Setting up service files for $mode mode..."
    
    # Copy and modify service file
    SERVICE_FILE="/etc/systemd/system/display.service"
    if [ -f "$SERVICE_FILE" ]; then
        echo "Service file already exists."
        if confirm "Do you want to overwrite it?"; then
            backup_file "$SERVICE_FILE"
            # Proceed with copying and modifying the service file
            sed -e "s|User=pi|User=$ACTUAL_USER|g" \
                -e "s|/home/pi|$ACTUAL_HOME|g" \
                "$ACTUAL_HOME/display_programme/docs/service/$service_source" > "$SERVICE_FILE"
            check_error "Failed to setup service file"
        else
            echo "Skipping service file setup."
        fi
    else
        # Proceed with copying and modifying the service file
        sed -e "s|User=pi|User=$ACTUAL_USER|g" \
            -e "s|/home/pi|$ACTUAL_HOME|g" \
            "$ACTUAL_HOME/display_programme/docs/service/$service_source" > "$SERVICE_FILE"
        check_error "Failed to setup service file"
    fi
    
    # Copy start script
    if [ -f "$ACTUAL_HOME/start_display.sh" ]; then
        echo "start_display.sh already exists."
        if confirm "Do you want to overwrite it?"; then
            backup_file "$ACTUAL_HOME/start_display.sh"
            su - "$ACTUAL_USER" -c "cp '$ACTUAL_HOME/display_programme/docs/service/$script_source' '$ACTUAL_HOME/start_display.sh'"
        else
            echo "Skipping start_display.sh."
        fi
    else
        su - "$ACTUAL_USER" -c "cp '$ACTUAL_HOME/display_programme/docs/service/$script_source' '$ACTUAL_HOME/start_display.sh'"
    fi
    check_error "Failed to copy start script"
}

# Create backup directory
mkdir -p "$BACKUP_DIR"
touch "$BACKUP_MANIFEST"

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

# Get actual username
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    ACTUAL_USER=$(logname)
fi
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

echo "Setting up for user: $ACTUAL_USER"
echo "Home directory: $ACTUAL_HOME"

# Check config.txt locations
CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
    if [ ! -f "$CONFIG_FILE" ]; then
        echo "Error: Could not find config.txt in /boot/firmware/ or /boot/"
        exit 1
    fi
fi
echo "Using config file: $CONFIG_FILE"

# Configure boot options
echo "Configuring boot options..."
NEED_REBOOT=0

# Enable SPI interface
echo "Enabling SPI interface..."
raspi-config nonint do_spi 0
check_error "Failed to enable SPI"

# Enable watchdog
echo "Setting up watchdog..."
if ! grep -q "dtparam=watchdog=on" "$CONFIG_FILE"; then
    echo "dtparam=watchdog=on" >> "$CONFIG_FILE"
    NEED_REBOOT=1
fi

# Enable dwc2 overlay for USB gadget support
echo "Enabling dwc2 overlay..."
DWC2_ADDED=0
if ! grep -q "^dtoverlay=dwc2$" "$CONFIG_FILE"; then
    echo "dtoverlay=dwc2" >> "$CONFIG_FILE"
    NEED_REBOOT=1
    DWC2_ADDED=1
fi

if [ $NEED_REBOOT -eq 1 ]; then
    echo "----------------------------------------"
    echo "Boot configuration has been updated."
    if [ $DWC2_ADDED -eq 1 ]; then
        echo "The dwc2 module has been enabled and requires a reboot before WebSerial setup."
        echo "The script will continue with other setup tasks,"
        echo "but WebSerial setup will be skipped until next reboot."
        SKIP_WEBSERIAL=1
    else
        echo "A reboot will be required to apply the hardware configuration changes."
    fi
    echo "The script will continue with the rest of the setup,"
    echo "and will offer to reboot at the end."
    echo "----------------------------------------"
fi

# Install required packages
echo "Installing required packages..."
apt-get update
check_error "Failed to update package list"

# Install dependencies
apt-get install -y git gh fonts-dejavu watchdog python3-dev network-manager libcairo2-dev pkg-config python3-dev python3-serial libmsgpack-dev build-essential fontconfig
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
# Clone repositories
echo "Cloning repositories..."
cd $ACTUAL_HOME
clone_repository "rpi_waiting_time_display" "display_programme"
check_error "Failed to clone display programme"

# After repository setup, run upgrade script
echo "Running system upgrades..."
sudo bash "$ACTUAL_HOME/display_programme/docs/service/upgrade.sh"
check_error "Failed to run upgrade script"

# Setup virtual environment
echo "Setting up virtual environment..."
if [ -d "$ACTUAL_HOME/display_env" ]; then
    echo "Virtual environment already exists."
    if confirm "Do you want to recreate it? This may remove any custom packages you've installed."; then
        rm -rf "$ACTUAL_HOME/display_env"
        su - $ACTUAL_USER -c "python3 -m venv $ACTUAL_HOME/display_env"
    else
        echo "Skipping virtual environment setup."
    fi
else
    su - $ACTUAL_USER -c "python3 -m venv $ACTUAL_HOME/display_env"
fi
check_error "Failed to create virtual environment"

# Install requirements
echo "Installing requirements..."
su - $ACTUAL_USER -c "source $ACTUAL_HOME/display_env/bin/activate && cd $ACTUAL_HOME/display_programme && pip install -r requirements.txt"
check_error "Failed to install display programme requirements"



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

# Copy and setup scripts
su - $ACTUAL_USER -c "cp $ACTUAL_HOME/display_programme/docs/service/switch_display_mode.sh $ACTUAL_HOME/switch_display_mode.sh"
su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/switch_display_mode.sh"

# Main installation process
# Use the already selected SETUP_MODE
case $SETUP_MODE in
    2)
        echo "Setting up Docker mode..."
        if [ ! -d "$ACTUAL_HOME/brussels_transit" ]; then
            echo "Cloning brussels transit repository..."
            cd "$ACTUAL_HOME"
            su - "$ACTUAL_USER" -c "git clone https://github.com/bdamokos/brussels_transit.git"
            check_error "Failed to clone brussels transit"
        else
            echo "Brussels transit repository already exists"
        fi
        setup_service_files "docker"
        # Install Docker if not present
        if ! command -v docker &> /dev/null; then
            curl -fsSL https://get.docker.com -o get-docker.sh
            sh get-docker.sh
            usermod -aG docker $ACTUAL_USER
            check_error "Failed to install Docker"
            rm -f get-docker.sh
            echo "Docker installed successfully"
        fi
        ;;
    3)
        echo "Setting up remote server mode..."
        echo "----------------------------------------"
        echo "Remote server mode selected. You will need to:"
        echo "1. Set up your remote backend server"
        echo "2. Edit your .env file to set BUS_API_BASE_URL to point to your remote server"
        echo "   For example: BUS_API_BASE_URL=https://your-server:5001"
        echo "----------------------------------------"
        setup_service_files "remote"
        ;;
    *)
        echo "Setting up normal mode..."
        if [ ! -d "$ACTUAL_HOME/brussels_transit" ]; then
            echo "Cloning brussels transit repository..."
            cd "$ACTUAL_HOME"
            su - "$ACTUAL_USER" -c "git clone https://github.com/bdamokos/brussels_transit.git"
            check_error "Failed to clone brussels transit"
        else
            echo "Brussels transit repository already exists"
        fi
        setup_service_files "normal"
        su - $ACTUAL_USER -c "source $ACTUAL_HOME/display_env/bin/activate && cd $ACTUAL_HOME/brussels_transit && pip install -r requirements.txt"
        check_error "Failed to install brussels transit requirements"
        ;;
esac

su - $ACTUAL_USER -c "chmod +x $ACTUAL_HOME/start_display.sh"

# Create .env file
if [ ! -f "$ACTUAL_HOME/display_programme/.env" ]; then
    echo "Creating .env file..."
    # Create with initial settings
    cat > "$ACTUAL_HOME/display_programme/.env" << EOF
UPDATE_MODE=$UPDATE_MODE
display_model=$DISPLAY_MODEL
EOF
    # Copy the example file as a reference, but commented out
    sed 's/^/# /' "$ACTUAL_HOME/display_programme/.env.example" >> "$ACTUAL_HOME/display_programme/.env"
    echo "Please edit the .env file with your settings (Lines starting with # are comments, to enable a setting, remove the #):"
    echo "nano $ACTUAL_HOME/display_programme/.env"
fi

# Set correct permissions for files and directories
echo "Setting up correct permissions..."
# Set ownership of all files in display_programme to the actual user
chown -R $ACTUAL_USER:$ACTUAL_USER "$ACTUAL_HOME/display_programme"
check_error "Failed to set ownership of display_programme directory"

# Set ownership of all files in brussels_transit to the actual user
if [ -d "$ACTUAL_HOME/brussels_transit" ]; then
    chown -R $ACTUAL_USER:$ACTUAL_USER "$ACTUAL_HOME/brussels_transit"
    check_error "Failed to set ownership of brussels_transit directory"
fi

# Create log directories with correct permissions
mkdir -p /var/log/display
chown $ACTUAL_USER:$ACTUAL_USER /var/log/display
chmod 755 /var/log/display

# Create and set permissions for specific log files
touch /var/log/display/display.out /var/log/display/display.err
chown $ACTUAL_USER:$ACTUAL_USER /var/log/display/display.out /var/log/display/display.err
chmod 644 /var/log/display/display.out /var/log/display/display.err

# Set permissions for config files
chmod 644 "$ACTUAL_HOME/display_programme/.env"*
chmod 644 "$ACTUAL_HOME/display_programme/requirements.txt"

# Set permissions for executable scripts
chmod +x "$ACTUAL_HOME/display_programme/docs/service/"*.sh
chmod +x "$ACTUAL_HOME/start_display.sh"
if [ -f "$ACTUAL_HOME/switch_display_mode.sh" ]; then
    chmod +x "$ACTUAL_HOME/switch_display_mode.sh"
fi

setup_uninstall

# Setup Samba if selected
if [ "$SETUP_SAMBA" = "yes" ]; then
    echo "Setting up Samba..."
    if [ -n "$SAMBA_PASSWORD" ]; then
        bash "$ACTUAL_HOME/display_programme/docs/service/setup_samba.sh" --password "$SAMBA_PASSWORD"
    else
        bash "$ACTUAL_HOME/display_programme/docs/service/setup_samba.sh"
    fi
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

# Setup network permissions
# Backup sysctl.conf before modification
if [ -f "/etc/sysctl.conf" ]; then
    backup_file "/etc/sysctl.conf"
fi

# Enable IP forwarding
if ! grep -q "net.ipv4.ip_forward=1" /etc/sysctl.conf; then
    echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
    sysctl -p
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

# Backup dnsmasq.conf before modification
if [ -f "/etc/dnsmasq.conf" ]; then
    backup_file "/etc/dnsmasq.conf"
fi

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
        # Add to REQUIRED_ENTRIES array
    "$ACTUAL_USER ALL=(ALL) NOPASSWD: /sbin/iptables -t nat"
    "$ACTUAL_USER ALL=(ALL) NOPASSWD: /usr/sbin/service dnsmasq restart"
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

# Check if fontconfig is available
if ! command -v fc-cache > /dev/null; then
    echo "fontconfig not found. Installing..."
    apt-get install -y fontconfig
    check_error "Failed to install fontconfig"
fi

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
    sudo fc-cache -f

    echo "Noto Emoji font installed successfully."
fi

# Verify installation
echo "Verifying Noto font installation..."
if fc-list | grep -i noto; then
    echo "Noto font verification successful."
else
    echo "Warning: Noto font not found in font list. This might affect emoji display."
fi

# Enable and start services with error checking
systemctl daemon-reload
systemctl enable display.service
check_error "Failed to enable display.service"
systemctl start display.service
check_error "Failed to start display.service"

# Start watchdog with error checking
systemctl enable watchdog
systemctl start watchdog
check_error "Failed to start watchdog service"


# Function to setup WebSerial support
setup_webserial() {
    echo "Setting up WebSerial support..."
    
    # Install the USB gadget script
    bash "$ACTUAL_HOME/display_programme/docs/service/setup_webserial.sh"
    check_error "Failed to setup USB gadget"
    
    # Copy and configure WebSerial service
    SERVICE_FILE="/etc/systemd/system/webserial.service"
    EXAMPLE_FILE="$ACTUAL_HOME/display_programme/docs/service/webserial.service.example"
    
    if [ -f "$SERVICE_FILE" ]; then
        backup_file "$SERVICE_FILE"
    fi
    
    if [ -f "$EXAMPLE_FILE" ]; then
        # Create a temporary file with username replaced
        TEMP_FILE=$(mktemp)
        sed "s|/home/pi|$ACTUAL_HOME|g" "$EXAMPLE_FILE" > "$TEMP_FILE"
        sed -i "s|User=pi|User=$ACTUAL_USER|g" "$TEMP_FILE"
        
        # Copy the modified file to systemd
        cp "$TEMP_FILE" "$SERVICE_FILE"
        rm "$TEMP_FILE"
        
        # Enable and start the service
        systemctl daemon-reload 
        systemctl enable webserial.service
        systemctl start webserial.service
        check_error "Failed to start WebSerial service"
        
        echo "WebSerial support installed successfully"
    else
        echo "Error: WebSerial service example file not found at $EXAMPLE_FILE"
        check_error "Failed to setup WebSerial service"
    fi
}

# After mode selection, install Webserial support if not skipped
if [ "$SKIP_WEBSERIAL" != "1" ]; then
    setup_webserial
else
    echo "----------------------------------------"
    echo "WebSerial setup has been skipped because dwc2 module was just enabled."
    echo "Please rerun 'sudo bash $ACTUAL_HOME/display_programme/docs/service/setup_webserial.sh'"
    echo "after the system reboots to complete WebSerial setup."
    echo "----------------------------------------"
fi

# Install Bluetooth WebSerial support (does not necessarily work)

echo "Setting up Bluetooth WebSerial support..."

# Install the Bluetooth serial script
bash "$ACTUAL_HOME/display_programme/docs/service/setup_bluetooth_serial.sh"
check_error "Failed to setup Bluetooth serial"

# Update webserial service to depend on bluetooth
SERVICE_FILE="/etc/systemd/system/webserial.service"
if [ -f "$SERVICE_FILE" ]; then
    # Add bluetooth.target to After and Wants if not already present
    if ! grep -q "After=.*bluetooth.target" "$SERVICE_FILE"; then
        sed -i '/^After=/ s/$/ bluetooth.target/' "$SERVICE_FILE"
    fi
    if ! grep -q "Wants=.*bluetooth.target" "$SERVICE_FILE"; then
        sed -i '/^Wants=/ s/$/ bluetooth.target/' "$SERVICE_FILE"
    fi
    
    # Reload systemd and restart webserial service
    systemctl daemon-reload
    systemctl restart webserial.service
    check_error "Failed to restart WebSerial service with Bluetooth support"
fi

echo "Bluetooth WebSerial support installed successfully"
echo "Your device will be discoverable as 'EPaperDisplay' for WebSerial connections"


echo "----------------------------------------"
echo "Setup completed!"
echo ""
echo "Your .env file contains your settings. "
echo "You can edit it manually if needed:"
echo "   nano $ACTUAL_HOME/display_programme/.env"
echo ""
echo "You can also edit your settings at http://$(hostname -I | cut -d' ' -f1).local:5002/debug/env or http://$(hostname).local:5002/debug/env once your Pi restarts." 
echo ""
echo "To uninstall in the future, run: sudo ~/uninstall_display.sh"
echo "You will find this readme at: https://github.com/bdamokos/rpi_waiting_time_display"
echo "----------------------------------------"

if [ "$AUTO_RESTART" = "yes" ]; then
    if [ $DWC2_ADDED -eq 1 ]; then
        echo "----------------------------------------"
        echo "The dwc2 module has been enabled and requires a reboot."
        echo "After reboot, please run:"
        echo "sudo bash $ACTUAL_HOME/display_programme/docs/service/setup_webserial.sh"
        echo "to complete the WebSerial setup."
        echo "----------------------------------------"
    fi
    echo "Restarting system in 5 seconds..."
    sleep 5
    reboot
else
    if [ $NEED_REBOOT -eq 1 ]; then
        echo "IMPORTANT: A reboot is required to apply the hardware configuration changes."
        if [ $DWC2_ADDED -eq 1 ]; then
            echo "After reboot, please run:"
            echo "sudo bash $ACTUAL_HOME/display_programme/docs/service/setup_webserial.sh"
            echo "to complete the WebSerial setup."
        fi
        echo "Please restart your system when convenient."
    else
        echo "Setup complete. A reboot is recommended but not required."
    fi
fi
