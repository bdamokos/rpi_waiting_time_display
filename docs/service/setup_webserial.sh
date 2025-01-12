#!/bin/bash

echo "----------------------------------------"
echo "WebSerial Setup Script"
echo "Version: 0.0.0 (2024-12-20)"
echo "----------------------------------------"

# Function for consistent logging
logger() {
    echo "$1"
    logger -t "webserial-setup" "$1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    logger "Please run as root"
    exit 1
fi

# Get actual username more reliably
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
elif [ -n "$DBUS_SESSION_BUS_ADDRESS" ]; then
    ACTUAL_USER=$(who | grep "$DBUS_SESSION_BUS_ADDRESS" | cut -d' ' -f1)
else
    # Try various methods to get the actual user
    for cmd in "logname" "who am i | cut -d' ' -f1" "who | grep tty | head -n1 | cut -d' ' -f1"; do
        ACTUAL_USER=$(eval "$cmd" 2>/dev/null) && break
    done
fi

if [ -z "$ACTUAL_USER" ]; then
    logger "Error: Could not determine the actual user"
    exit 1
fi

ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")
logger "Setting up for user: $ACTUAL_USER (home: $ACTUAL_HOME)"

# Load required modules
logger "Loading USB modules..."
modprobe libcomposite || logger "Warning: Failed to load libcomposite module"
modprobe usb_f_acm || logger "Warning: Failed to load usb_f_acm module"

# Create gadget
cd /sys/kernel/config/usb_gadget/ || { logger "Error: USB gadget config directory not found"; exit 1; }

# Remove existing gadget if it exists
if [ -d "pi4" ]; then
    logger "Removing existing gadget configuration..."
    cd pi4
    if [ -f "UDC" ]; then
        echo "" > UDC
    fi
    rm -f configs/c.1/acm.usb0
    cd ..
    rmdir pi4 2>/dev/null || logger "Warning: Could not remove old gadget directory"
fi

logger "Creating new USB gadget..."
mkdir -p pi4
cd pi4 || { logger "Error: Could not create/enter gadget directory"; exit 1; }

# USB IDs
logger "Configuring USB device..."
echo 0x1209 > idVendor  # pid.codes VID
echo 0x0001 > idProduct # Testing PID
echo 0x0200 > bcdUSB   # USB 2.0
echo 0x0100 > bcdDevice # v1.0.0

# Set device class to vendor-specific
echo 0xFF > bDeviceClass
echo 0x00 > bDeviceSubClass
echo 0x00 > bDeviceProtocol

# Create strings
mkdir -p strings/0x409
echo "fedcba9876543210" > strings/0x409/serialnumber
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "E-Paper Display Setup" > strings/0x409/product

# Create configuration
mkdir -p configs/c.1/strings/0x409
echo "Config 1" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

# Create ACM function
mkdir -p functions/acm.usb0
ln -sf functions/acm.usb0 configs/c.1/

# Enable gadget
UDC=$(ls /sys/class/udc)
if [ -z "$UDC" ]; then
    logger "Error: No UDC found"
    exit 1
fi
echo "$UDC" > UDC || logger "Warning: Could not write to UDC"

# Copy and configure WebSerial service with correct username
logger "Setting up WebSerial service..."
SERVICE_FILE="/etc/systemd/system/webserial.service"
EXAMPLE_FILE="$ACTUAL_HOME/display_programme/docs/service/webserial.service.example"

if [ -f "$EXAMPLE_FILE" ]; then
    logger "Found service example file"
    # Create a temporary file with username replaced
    TEMP_FILE=$(mktemp)
    sed "s|/home/pi|$ACTUAL_HOME|g" "$EXAMPLE_FILE" > "$TEMP_FILE"
    sed -i "s|User=pi|User=$ACTUAL_USER|g" "$TEMP_FILE"
    
    # Copy the modified file to systemd
    cp "$TEMP_FILE" "$SERVICE_FILE"
    rm "$TEMP_FILE"
    
    # Enable and start service
    systemctl daemon-reload
    systemctl enable webserial.service
    systemctl start webserial.service
    
    logger "WebSerial service installed and started"
else
    logger "Error: WebSerial service example file not found at $EXAMPLE_FILE"
    exit 1
fi

logger "WebSerial setup complete" 