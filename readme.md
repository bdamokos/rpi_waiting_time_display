# Waiting Times Pi Display

A Raspberry Pi project that displays bus waiting times using an e-Paper display (Waveshare 2.13" G V2).
![Display Example](docs/images/display_example.jpg)

The display shows:
- Current time
- Weather conditions and temperature
- Next bus arrival times for configured lines
- Color-coded bus line numbers matching STIB/MIVB official colors


# Requirements
The server from https://github.com/bdamokos/brussels_transit is set up and is providing data for the stop we are interested in.

An API key for OpenWeatherMap is required to get the weather data.

## Hardware
Tested with:
- Raspberry Pi Zero 2W
- Waveshare 2.13" G V2 e-Paper display (black, white, red, yellow; no partial refresh support)

# Configuration
The .env file is used to configure the application. It contains the API keys and the parameters for the weather and bus services.

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


# Specific workarounds (Waveshare 2.13 inch display with 4 colours, revision 2)
To get the display working, I needed to copy a specific file from the E-Paper library from 
e-Paper/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g.py
to the waveshare_epd folder in the virtual environment.

The four colour version of the display does not support partial refresh, so it flickers with every refresh, making it less ideal for this application, despite the nice colours.