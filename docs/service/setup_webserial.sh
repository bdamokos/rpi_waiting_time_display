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

echo "Setting up for user: $ACTUAL_USER"
echo "Home directory: $ACTUAL_HOME"

# Load required modules
echo "Loading kernel modules..."
if ! modprobe libcomposite; then
    echo "Error: Failed to load libcomposite module"
    exit 1
fi
if ! modprobe usb_f_acm; then
    echo "Error: Failed to load usb_f_acm module"
    exit 1
fi
echo "Kernel modules loaded successfully"

# Create gadget
echo "Creating USB gadget..."
cd /sys/kernel/config/usb_gadget/

# Clean up any existing gadget
if [ -d "pi4" ]; then
    echo "Cleaning up existing gadget configuration..."
    cd pi4
    if [ -f "UDC" ]; then
        echo "" > UDC
    fi
    rm -f configs/c.1/acm.usb0
    cd ..
    rmdir pi4 2>/dev/null || true
fi

mkdir -p pi4
cd pi4

# USB IDs
echo "Configuring USB device parameters..."
echo 0x1209 > idVendor  # pid.codes VID
echo 0x0001 > idProduct # Testing PID
echo 0x0200 > bcdUSB   # USB 2.0
echo 0x0100 > bcdDevice # v1.0.0

# Set device class to vendor-specific
echo 0xFF > bDeviceClass
echo 0x00 > bDeviceSubClass
echo 0x00 > bDeviceProtocol

# Create strings
echo "Setting up USB device strings..."
mkdir -p strings/0x409
echo "fedcba9876543210" > strings/0x409/serialnumber
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "E-Paper Display Setup" > strings/0x409/product

# Create configuration
echo "Creating USB configuration..."
mkdir -p configs/c.1/strings/0x409
echo "Config 1" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

# Create ACM function
echo "Setting up ACM function..."
mkdir -p functions/acm.usb0
ln -s functions/acm.usb0 configs/c.1/

# Enable gadget
echo "Enabling USB gadget..."
sleep 2  # Give the system time to initialize the USB controller
UDC=$(ls /sys/class/udc)
if [ -z "$UDC" ]; then
    echo "Error: No USB Device Controller found"
    echo "Available USB controllers:"
    ls -l /sys/class/udc/
    echo "Please ensure dwc2 module is loaded and working"
    exit 1
fi
echo "Found USB Device Controller: $UDC"

if ! echo "$UDC" > UDC; then
    echo "Error: Failed to enable USB gadget with controller $UDC"
    echo "Current USB gadget state:"
    cat UDC
    exit 1
fi
echo "USB gadget enabled successfully"

# Copy and configure WebSerial service with correct username
echo "Setting up WebSerial service..."
SERVICE_FILE="/etc/systemd/system/webserial.service"
EXAMPLE_FILE="$ACTUAL_HOME/display_programme/docs/service/webserial.service.example"

if [ -f "$EXAMPLE_FILE" ]; then
    echo "Found WebSerial service example file"
    # Create a temporary file with username replaced
    TEMP_FILE=$(mktemp)
    sed "s|/home/pi|$ACTUAL_HOME|g" "$EXAMPLE_FILE" > "$TEMP_FILE"
    sed -i "s|User=pi|User=$ACTUAL_USER|g" "$TEMP_FILE"
    
    # Copy the modified file to systemd
    cp "$TEMP_FILE" "$SERVICE_FILE"
    rm "$TEMP_FILE"
    
    # Enable and start service
    echo "Configuring systemd service..."
    systemctl daemon-reload
    systemctl enable webserial.service
    systemctl start webserial.service
    
    # Check service status
    echo "Checking WebSerial service status..."
    systemctl status webserial.service
    
    echo "WebSerial service installed and started"
else
    echo "Error: WebSerial service example file not found at $EXAMPLE_FILE"
    exit 1
fi

echo "WebSerial setup complete" 