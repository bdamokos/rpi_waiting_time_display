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
echo "Version: 0.0.5 (2024-12-05)"  # AUTO-INCREMENT
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

# Install Python development headers
apt-get install -y git gh fonts-dejavu watchdog python3-dev
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

# Setup service files
echo "Setting up service files..."
# Copy and modify service file
sed "s/User=pi/User=$ACTUAL_USER/g" $ACTUAL_HOME/display_programme/docs/service/display.service.example > /etc/systemd/system/display.service
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

# Enable and start service
systemctl daemon-reload
systemctl enable display.service
systemctl start display.service

echo "----------------------------------------"
echo "Setup completed!"
echo ""
echo "Next steps:"
echo "1. Edit your .env file: nano $ACTUAL_HOME/display_programme/.env"
echo "2. Check service status: systemctl status display.service"
echo "3. View logs: journalctl -u display.service -f"
echo ""
echo "The service will start automatically on boot."
setup_uninstall
echo ""
echo "To uninstall in the future, run: sudo ~/uninstall_display.sh"
echo "----------------------------------------"