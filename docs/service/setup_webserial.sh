#!/bin/bash

echo "----------------------------------------"
echo "WebSerial Setup Script"
echo "Version: 0.0.0 (2024-12-20)"
echo "----------------------------------------"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Get actual username
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    ACTUAL_USER=$(logname)
fi
ACTUAL_HOME=$(eval echo "~$ACTUAL_USER")

# Load required modules
modprobe libcomposite
modprobe usb_f_acm

# Create gadget
cd /sys/kernel/config/usb_gadget/
mkdir -p pi4
cd pi4

# USB IDs
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
ln -s functions/acm.usb0 configs/c.1/

# Enable gadget
UDC=$(ls /sys/class/udc)
echo $UDC > UDC

# Copy and configure WebSerial service with correct username
echo "Setting up WebSerial service..."
SERVICE_FILE="/etc/systemd/system/webserial.service"
EXAMPLE_FILE="$ACTUAL_HOME/display_programme/docs/service/webserial.service.example"

if [ -f "$EXAMPLE_FILE" ]; then
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
    
    echo "WebSerial service installed and started"
else
    echo "Error: WebSerial service example file not found at $EXAMPLE_FILE"
    exit 1
fi

echo "WebSerial setup complete" 