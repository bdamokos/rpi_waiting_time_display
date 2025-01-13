#!/bin/bash

echo "----------------------------------------"
echo "WebSerial Setup Script"
echo "Version: 0.0.6 (2025-01-13)"  # AUTO-INCREMENT
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

# Add required modules to /etc/modules
echo "Adding required modules to /etc/modules..."
for module in dwc2 libcomposite; do
    if ! grep -q "^$module$" /etc/modules; then
        echo "$module" >> /etc/modules
    fi
done

# Create USB gadget configuration script
echo "Creating USB gadget configuration script..."
cat > /usr/local/bin/setup-usb-gadget.sh << 'EOF'
#!/bin/bash

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
    # Remove existing symlinks first
    rm -f configs/c.1/acm.0
    # Clean up directories if they exist
    [ -d configs/c.1/strings/0x409 ] && rmdir configs/c.1/strings/0x409
    [ -d configs/c.1 ] && rmdir configs/c.1
    [ -d functions/acm.0 ] && rmdir functions/acm.0
    [ -d strings/0x409 ] && rmdir strings/0x409
    cd ..
    rmdir pi4
fi

mkdir -p pi4
cd pi4

# USB IDs - using standard CDC ACM values
echo 0x0483 > idVendor # Standard Test vendor ID
echo 0x5740 > idProduct # Standard CDC ACM product ID
echo 0x0200 > bcdUSB # USB 2.0
echo 0x0100 > bcdDevice # v1.0.0
echo 0x02 > bDeviceClass # Communications Device Class
echo 0x00 > bDeviceSubClass
echo 0x00 > bDeviceProtocol

# USB strings
mkdir -p strings/0x409
echo "fedcba9876543210" > strings/0x409/serialnumber
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "Pi Zero Serial" > strings/0x409/product

# Create configuration
mkdir -p configs/c.1/strings/0x409
echo "CDC ACM Config" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

# Create Serial function
mkdir -p functions/acm.0
ln -s functions/acm.0 configs/c.1/

# Enable gadget
UDC=$(ls /sys/class/udc)
if [ -n "$UDC" ]; then
    echo "$UDC" > UDC
fi
EOF

chmod +x /usr/local/bin/setup-usb-gadget.sh

# Create systemd service (matching the working setup)
echo "Creating USB gadget service..."
cat > /etc/systemd/system/usb_serial_gadget.service << 'EOF'
[Unit]
Description=USB Serial Gadget
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/setup-usb-gadget.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

# Enable and start the service
systemctl daemon-reload
systemctl enable usb_serial_gadget.service
systemctl start usb_serial_gadget.service

# Copy and configure WebSerial service
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