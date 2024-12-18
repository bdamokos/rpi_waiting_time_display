# Setting up the Raspberry Pi

## Step 1: Initial Setup (Developer)

### Prepare the SD card
Using Raspberry Pi Imager, download the Raspberry Pi OS Lite (64-bit) or Raspberry Pi OS Desktop (64-bit) image onto a microSD card.

![Raspberry Pi Imager](images/rpi_imager_1.png)

Under settings:
- Enable SSH
- Set up username and password
- Input WiFi network name and password
- Check the hostname (default is raspberrypi.local)

### Initial Hardware Assembly
The hardware setup is quite straightforward:
- If you have a case, follow the instructions in the case's documentation. With the case I had, this included:
    - Adding a thermal pad to the bottom of the case
    - Screwing the Raspberry Pi into the case with 4 screws

    ![Raspberry Pi inserted into the bottom of the case, held in place by up to 4 screws (3 shown in the image)](images/hardware_setup_insert_screen_into_case.jpeg)

    - Removing the film from the back of the screen and sticking it to the top of the case
    - Carefully aligning the pin sockets on the display with the pins on the Raspberry Pi and firmly pressing them together
    - Plug in the microSD card
    - Plugging in the display to either USB-C (with the adapter) or micro-USB (important, that one USB port is for power only, the second for data, this is marked on the case)
![Raspberry Pi side view with power plugged in to the correct port](images/hardware_setup_finished_side.png)

- Without a case, you just need to press the display into the Raspberry Pi, making sure that you seat the screen firmly onto the pins (the bottom of the display's board should more or less touch the top of the Raspberry Pi's board), and plug in the microSD card.

### Initial Software Setup
1. Power on the Raspberry Pi and wait for it to connect to WiFi
2. Connect to it via SSH: `ssh <username>@raspberrypi.local`
3. Download and run the setup script:
``` bash
# Download the setup script (with cache bypass)
curl -H "Cache-Control: no-cache" -O https://raw.githubusercontent.com/bdamokos/rpi_waiting_time_display/main/setup_display.sh
# Make it executable
chmod +x setup_display.sh
```
![Fast Setup Step 2](images/fast_setup_step2.png) 
``` bash
# Run the setup script
sudo ./setup_display.sh
```

The script will:
- Enable SPI interface
- Install all required packages
- Set up watchdog
- Clone repositories
- Set up virtual environment
- Install requirements
- Configure and start the service

## Step 2: Final Setup (End User)

### Connect Your Display
1. Insert the microSD card into your Raspberry Pi (if not already inserted)
2. Connect your Raspberry Pi to power using the USB cable
3. Wait for the display to show the setup QR code
4. Scan the QR code with your phone or visit this page on your computer
5. Click the "Connect Device" button above

### Configure Your Display
The setup wizard will guide you through:
1. Connecting to your WiFi network
2. Setting up your location for weather information
3. Selecting your bus/tram stops
4. Optional: Configuring flight tracking

After completing the wizard, your display will automatically update and show:
- Current weather conditions
- Next bus/tram arrival times
- Overhead flights (if configured)

![Assembled and configured display](images/hardware_setup_finished_top.png)

# Setting up the backend server
:warning: **Important:** The backend server needs to be set up for the display to work (otherwise the display will only display the weather). See the [backend server readme](https://github.com/bdamokos/brussels_transit) for more information. If the API keys are not configured, the service will not start.

**Currently the set up script installs the backend server, but it does not configure it.** You need to set up the API keys manually and make sure that the backend server is monitoring the same stops as are requested by your display.

:warning: **Note:** The display requires internet access to show transit times and weather information. Without internet, it will display a QR code to help you connect to WiFi.