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

# Configuration
The .env file is used to configure the application. It contains the API keys and the parameters for the weather and bus services.



# Specific workarounds (Waveshare 2.13 inch display with 4 colours, revision 2)
To get the display working, I needed to copy a specific file from the E-Paper library from 
e-Paper/E-paper_Separate_Program/2in13_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd2in13g.py
to the waveshare_epd folder in the virtual environment.