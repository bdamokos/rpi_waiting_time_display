I'll update the web_serial_lessons.md with our findings:

````markdown:web_serial_lessons.md
# Web Serial Implementation Lessons

## Summary of Findings

### What Works
1. CDC ACM USB Gadget
   - Using standard CDC ACM function
   - Vendor ID: 0x1209 (pid.codes)
   - Product ID: 0x0001
   - Device class: Vendor specific (0xFF)
   - Simple configuration with one interface

2. WebSerial API
   - Modern web API designed for serial communication
   - Automatically handles CDC ACM devices
   - No need for manual interface claiming
   - Built-in support for standard serial parameters

3. Two-way Communication
   - Browser ↔ Pi communication working
   - Standard serial parameters (115200 baud, 8N1)
   - Reliable message passing with newline termination

### What Doesn't Work
1. WebUSB Approach
   - Unable to claim interface (kernel driver conflict)
   - More complex implementation
   - Less suitable for serial communication
   - Requires manual interface handling

## Working Implementation

### 1. USB Gadget Setup
````bash:docs/setup/setup_cdc_acm.sh
#!/bin/bash
# Load required modules
modprobe libcomposite
modprobe usb_f_acm

# Create gadget
cd /sys/kernel/config/usb_gadget/
mkdir -p pi4
cd pi4

# USB IDs - Match WebUSB test page expectations
echo 0x1209 > idVendor  # pid.codes VID
echo 0x0001 > idProduct # Testing PID (we don't have €6000 to get a real one)
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
echo "Pi WebUSB Device" > strings/0x409/product

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
````

### 2. Pi Serial Echo Script
- Handles serial communication on Pi side
- Echoes received messages with prefix
- Proper cleanup on exit
- Shows both hex and string data for debugging

### 3. WebSerial Interface
- Uses modern WebSerial API
- Proper connection management
- Reliable cleanup on disconnect
- Error handling and recovery

## Failed Approaches

### 1. WebUSB Implementation
- Attempted to use WebUSB API
- Issues with interface claiming
- Kernel driver conflicts
- More complex than necessary for serial communication

### 2. FunctionFS Approach
- Tried using FunctionFS for custom USB function
- Complicated setup
- Unreliable device state
- Not necessary for simple serial communication

## Lessons Learned

1. Choose the Right API
   - WebSerial is purpose-built for serial communication
   - Simpler implementation than WebUSB
   - Better browser support for serial devices

2. USB Gadget Configuration
   - Keep it simple with standard CDC ACM
   - Vendor-specific class works well
   - No need for complex USB descriptors

3. Connection Management
   - Proper cleanup is essential
   - Handle disconnects gracefully
   - Release resources properly

4. Error Handling
   - Robust error handling in both directions
   - Proper cleanup on errors
   - Clear status messages to user

