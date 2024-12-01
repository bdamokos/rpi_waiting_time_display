# Waiting Times Pi Display

A Raspberry Pi project that displays bus waiting times using an e-Paper display (Waveshare 2.13" G V2).
![Display Example](docs/images/display_example.jpg)

The display shows:
- Current time
- Weather conditions and temperature (including a weather mode when no bus is coming soon)
![Weather Mode](docs/images/weather%20mode%20with%20dithered%20weather%20icons.png)

- Next bus arrival times for configured lines
- Color-coded bus line numbers matching STIB/MIVB official colors


# Requirements
The server from https://github.com/bdamokos/brussels_transit is set up and is providing data for the stop we are interested in.

An API key for OpenWeatherMap is required to get the weather data.

## Hardware
Tested with:
- Raspberry Pi Zero 2W (~€20 for the board, €10-15 for microSD card, €8 for charger)
- Waveshare 2.13" G V2 e-Paper display (black, white, red, yellow; no partial refresh support; ~€20)

# Configuration
The .env file is used to configure the application:
- Add your openweather API key
- Input your location
- Configure the monitored transit stops
- Configure your display model

The [start_display.sh](docs/service/start_display.sh.example) script is used to start the display service. It should be copied to the home directory and made executable.

A virtual environment is used to run the application. The dependencies are listed in the [requirements.txt](requirements.txt) file. By default it is set up in the ~/display_env directory with:
```
python3 -m venv ~/display_env
source ~/display_env/bin/activate
pip install -r requirements.txt
```

To set up the service with systemd, copy the [start_display.service](docs/service/start_display.service.example) file to the /etc/systemd/system directory and enable it with:
```
sudo systemctl enable start_display.service
sudo systemctl start start_display.service
```
If you don't already have the DejaVuSans font installed, you can install it with:
```
sudo apt-get install ttf-dejavu
```

To setup watchdog (in case the display freezes, it will reboot the Pi):

Add these parameters to /boot/firmware/config.txt:
```
dtparam=watchdog=on
```

Then install watchdog:
```
sudo apt-get install watchdog
```

Edit the watchdog configuration file:
```
sudo nano /etc/watchdog.conf
```
Put in the following:
```
# Add or uncomment these lines:
watchdog-device = /dev/watchdog
watchdog-timeout = 15
interval = 10
max-load-1 = 3.0
max-load-5 = 2.8
```

Then enable the watchdog service:
```
sudo systemctl enable watchdog
sudo systemctl start watchdog
```

# Specific workarounds (Waveshare 2.13 inch display with 4 colours, revision 2)
To get the display working, I needed to copy a specific file from the E-Paper library from 
e-Paper/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g.py
to the waveshare_epd folder in the virtual environment.

The four colour version of the display does not support partial refresh, so it flickers with every refresh, making it less ideal for this application, despite the nice colours.