#!/bin/bash
echo "----------------------------------------"
echo "USB Gadget Setup Script"
echo "Version: 0.0.0 (2024-12-18)"  # AUTO-INCREMENT
echo "----------------------------------------"
echo "MIT License - Copyright (c) 2024 Bence Damokos"
echo "----------------------------------------"

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root"
    exit 1
fi

# Enable dwc2 driver
if ! grep -q "dtoverlay=dwc2" /boot/config.txt; then
    echo "dtoverlay=dwc2" >> /boot/config.txt
fi

if ! grep -q "modules-load=dwc2" /boot/cmdline.txt; then
    sed -i '1s/$/ modules-load=dwc2/' /boot/cmdline.txt
fi

# Create the USB gadget configuration script
cat > /usr/local/sbin/usb_gadget_setup.sh << 'EOL'
#!/bin/bash

modprobe libcomposite
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

# Link everything up and bind the USB device
ls /sys/class/udc > UDC
EOL

chmod +x /usr/local/sbin/usb_gadget_setup.sh

# Create systemd service
cat > /etc/systemd/system/usb_gadget.service << 'EOL'
[Unit]
Description=WebUSB Gadget Setup
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/usb_gadget_setup.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOL

# Enable and start the service
systemctl enable usb_gadget.service
systemctl start usb_gadget.service 