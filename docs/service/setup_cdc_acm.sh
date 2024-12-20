#!/bin/bash

# Manual setup for CDC ACM in case the automatic setup fails

echo "Version: 0.0.0 (2024-12-20)" # AUTO-INCREMENT

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Cleanup any existing gadget
if [ -d "/sys/kernel/config/usb_gadget/pi4" ]; then
    cd /sys/kernel/config/usb_gadget/pi4
    echo "" > UDC
    rm -f configs/c.1/acm.usb0
    rmdir configs/c.1/strings/0x409 2>/dev/null
    rmdir configs/c.1 2>/dev/null
    rmdir functions/acm.usb0 2>/dev/null
    rmdir strings/0x409 2>/dev/null
    cd ..
    rmdir pi4 2>/dev/null
fi

# Load required modules
modprobe libcomposite
modprobe usb_f_acm

# Create gadget
cd /sys/kernel/config/usb_gadget/
mkdir -p pi4
cd pi4

# USB IDs - Match WebUSB test page expectations
echo 0x1209 > idVendor  # pid.codes VID
echo 0x0001 > idProduct # Our assigned PID
echo 0x0200 > bcdUSB   # USB 2.0
echo 0x0100 > bcdDevice # v1.0.0

# Set device class to vendor-specific
echo 0xFF > bDeviceClass      # Vendor specific
echo 0x00 > bDeviceSubClass
echo 0x00 > bDeviceProtocol

# Strings
mkdir -p strings/0x409
echo "fedcba9876543210" > strings/0x409/serialnumber
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "Pi WebUSB Device" > strings/0x409/product

# Configuration
mkdir -p configs/c.1/strings/0x409
echo "Config 1" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

# Create ACM function
mkdir -p functions/acm.usb0
ln -s functions/acm.usb0 configs/c.1/

# Enable gadget
UDC=$(ls /sys/class/udc)
echo $UDC > UDC

ls -l /dev/ttyGS0