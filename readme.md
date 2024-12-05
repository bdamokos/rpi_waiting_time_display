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

# Setting up the Raspberry Pi
See [docs/setting up the Rpi.md](docs/setting%20up%20the%20Rpi.md)

## Uninstalling the display
Run [docs/service/uninstall_display.sh](docs/service/uninstall_display.sh) (which is copied to the home directory during setup or manually:
``` bash
curl -O https://raw.githubusercontent.com/bdamokos/rpi_waiting_time_display/main/docs/service/uninstall_display.sh
chmod +x uninstall_display.sh
sudo ./uninstall_display.sh
```

# Specific workarounds (Waveshare 2.13 inch display with 4 colours, revision 2)
To get the display working, I needed to copy a specific file from the E-Paper library from 
e-Paper/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g.py
to the waveshare_epd folder in the virtual environment.

The four colour version of the display does not support partial refresh, so it flickers with every refresh, making it less ideal for this application, despite the nice colours.

# Known issues
- 
