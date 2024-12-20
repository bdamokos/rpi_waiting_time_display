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

# Create systemd service
cat > /etc/systemd/system/webserial.service << EOL
[Unit]
Description=WebSerial Configuration Interface
After=network.target
Wants=network.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /home/pi/display_programme/webserial_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOL

# Enable and start service
systemctl daemon-reload
systemctl enable webserial.service
systemctl start webserial.service

echo "WebSerial setup complete" 