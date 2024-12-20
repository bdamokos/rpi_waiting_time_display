#!/bin/bash

# Load required modules
modprobe libcomposite
modprobe dwc2

# Wait for UDC to be available (up to 10 seconds)
for i in {1..10}; do
    if [ -d "/sys/class/udc" ] && [ "$(ls /sys/class/udc)" != "" ]; then
        break
    fi
    echo "Waiting for UDC to be available... ($i/10)"
    sleep 1
done

if [ ! -d "/sys/class/udc" ] || [ "$(ls /sys/class/udc)" == "" ]; then
    echo "Error: No UDC available. Make sure dwc2 is in peripheral mode."
    exit 1
fi

# Clean up any existing configuration
if [ -d "/sys/kernel/config/usb_gadget/pi4" ]; then
    cd /sys/kernel/config/usb_gadget/pi4
    if [ -f "UDC" ]; then
        echo "" > UDC
    fi
    rm -f configs/c.1/webusb.0
    rm -f configs/c.1/strings/0x409/configuration
    rmdir configs/c.1/strings/0x409 2>/dev/null || true
    rmdir configs/c.1 2>/dev/null || true
    rm -f strings/0x409/serialnumber
    rm -f strings/0x409/manufacturer
    rm -f strings/0x409/product
    rmdir strings/0x409 2>/dev/null || true
    rm -f functions/webusb.0/* 2>/dev/null || true
    rmdir functions/webusb.0 2>/dev/null || true
    rmdir functions 2>/dev/null || true
    cd ..
    rmdir pi4 2>/dev/null || true
fi

cd /sys/kernel/config/usb_gadget/
mkdir -p pi4
cd pi4

# USB device configuration for WebUSB
echo 0x1209 > idVendor  # pid.codes (open-source USB VID)
echo 0x0001 > idProduct # Our custom PID
echo 0x0100 > bcdDevice # v1.0.0
echo 0x0200 > bcdUSB    # USB2

# Device info
mkdir -p strings/0x409
echo "fedcba9876543210" > strings/0x409/serialnumber
echo "Raspberry Pi" > strings/0x409/manufacturer
echo "Pi Zero WebUSB Setup" > strings/0x409/product

# Create configuration
mkdir -p configs/c.1/strings/0x409
echo "WebUSB Configuration" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower

# Add WebUSB specific descriptors
mkdir -p os_desc
echo 1 > os_desc/use
echo 0xcd > os_desc/b_vendor_code
echo MSFT100 > os_desc/qw_sign

# Create WebUSB function
mkdir -p functions/webusb.0
ln -s functions/webusb.0 configs/c.1/

# Link everything up and bind the USB device
UDC=$(ls /sys/class/udc)
if [ -z "$UDC" ]; then
    echo "Error: No UDC available"
    exit 1
fi

# Try to bind the device
for i in {1..5}; do
    if echo "$UDC" > UDC 2>/dev/null; then
        echo "Successfully bound to $UDC"
        exit 0
    fi
    echo "Attempt $i: Device busy, waiting..."
    sleep 1
done

echo "Failed to bind to UDC after 5 attempts"
exit 1 