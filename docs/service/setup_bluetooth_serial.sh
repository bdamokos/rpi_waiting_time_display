#!/bin/bash

echo "Version: 0.0.3 (2024-12-21)"  # AUTO-INCREMENT

# Check if Bluetooth is disabled in config.txt or dtoverlay
if grep -q "^dtoverlay=disable-bt\|^dtoverlay=pi3-disable-bt" /boot/config.txt; then
    echo "Bluetooth is currently disabled in /boot/config.txt"
    echo "Removing disable-bt overlay..."
    sed -i '/^dtoverlay=.*disable-bt.*/d' /boot/config.txt
    echo "Bluetooth enabled in config.txt"
    echo "You'll need to reboot for this change to take effect"
    echo "Please run this script again after rebooting"
    exit 0
fi

# Check if UART is configured correctly for Bluetooth
if ! grep -q "^enable_uart=1" /boot/config.txt; then
    echo "Enabling UART for Bluetooth..."
    echo "enable_uart=1" >> /boot/config.txt
    echo "UART enabled in config.txt"
    echo "You'll need to reboot for this change to take effect"
    echo "Please run this script again after rebooting"
    exit 0
fi

# Get Bluetooth adapter address
BT_ADDR=$(hcitool dev | grep -o "[[:xdigit:]:]\{17\}")
if [ -z "$BT_ADDR" ]; then
    echo "No Bluetooth adapter found!"
    echo "This could be because:"
    echo "1. Bluetooth is disabled in hardware"
    echo "2. The system needs a reboot after enabling Bluetooth"
    echo "3. The Bluetooth adapter is not working"
    echo ""
    echo "Please try rebooting first. If the issue persists, check:"
    echo "- /boot/config.txt for Bluetooth configuration"
    echo "- 'sudo systemctl status bluetooth' for service status"
    echo "- 'hciconfig -a' for adapter status"
    exit 1
fi
echo "Bluetooth adapter address: $BT_ADDR"

# Check if Bluetooth is disabled in config.txt
if grep -q "^dtoverlay=disable-bt" /boot/firmware/config.txt; then
    echo "Bluetooth is currently disabled. Enabling..."
    sed -i '/^dtoverlay=disable-bt/d' /boot/firmware/config.txt
    echo "Bluetooth enabled in config.txt"
    echo "You'll need to reboot for this change to take effect"
fi

# Check if Bluetooth service is enabled
if ! systemctl is-enabled bluetooth.service > /dev/null 2>&1; then
    echo "Enabling Bluetooth service..."
    systemctl enable bluetooth.service
fi

# Start Bluetooth service if not running
if ! systemctl is-active bluetooth.service > /dev/null 2>&1; then
    echo "Starting Bluetooth service..."
    systemctl start bluetooth.service
fi

# Install required packages
sudo apt-get update
sudo apt-get install -y bluetooth bluez bluez-tools

# Configure Bluetooth settings
cat > /etc/bluetooth/main.conf << EOL
[General]
Name = EPaperDisplay
Class = 0x000100
DiscoverableTimeout = 0
PairableTimeout = 0
EOL

# Restart bluetooth to apply settings
systemctl restart bluetooth

# Make device discoverable
echo "Making Bluetooth adapter discoverable..."
hciconfig hci0 piscan

# Set up Serial Port Profile
sdptool add SP

# Create rfcomm binding
# Note: You might need to adjust the MAC address and channel
echo "rfcomm0 {
  bind yes;
  # Listen on any device
  device *;
  channel 1;
  comment 'Serial Port';
}" | sudo tee /etc/bluetooth/rfcomm.conf

# Create udev rule for rfcomm0
echo 'KERNEL=="rfcomm[0-9]*", GROUP="dialout", MODE="0660"' | sudo tee /etc/udev/rules.d/45-rfcomm.rules

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Start listening for connections
# Create a PID file directory
mkdir -p /var/run/bluetooth

# Start rfcomm listen and save PID
rfcomm listen /dev/rfcomm0 1 > /var/run/bluetooth/rfcomm.log 2>&1 &
echo $! > /var/run/bluetooth/rfcomm.pid

# Wait a moment to ensure the process started
sleep 1

# Check if the process is running
if kill -0 $(cat /var/run/bluetooth/rfcomm.pid) 2>/dev/null; then
    echo "rfcomm listening service started successfully"
else
    echo "Failed to start rfcomm listening service"
    exit 1
fi

# Add current user to dialout group if not already added
if ! groups $USER | grep -q "\bdialout\b"; then
    sudo usermod -a -G dialout $USER
    echo "Added $USER to dialout group"
    echo "You'll need to log out and back in for this to take effect"
fi

echo "Setup complete!"
echo "----------------------------------------"
echo "Your Raspberry Pi is now discoverable as 'EPaperDisplay'"
echo "Bluetooth MAC Address: $BT_ADDR"
echo "Serial Port Profile is enabled on channel 1"
echo "----------------------------------------"
echo "To connect from a browser:"
echo "1. Go to the WebSerial setup page"
echo "2. Click 'Connect Device'"
echo "3. Select 'Bluetooth' in the device picker"
echo "4. Select 'EPaperDisplay' from the list"
echo "----------------------------------------"