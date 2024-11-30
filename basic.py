#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
if os.path.exists(libdir):
    sys.path.append(libdir)

import logging
from waveshare_epd import epd2in13g_V2
import time
from PIL import Image, ImageDraw, ImageFont
from weather import WeatherService
from bus_service import BusService

logging.basicConfig(level=logging.DEBUG)

# Weather icon mapping
WEATHER_ICONS = {
    'Clear': '☀',
    'Clouds': '☁',
    'Rain': '🌧',
    'Snow': '❄',
    'Thunderstorm': '⚡',
    'Drizzle': '🌦',
    'Mist': '🌫',
}

def update_display(epd, weather_data, bus_data, error_message=None, first_run=False):
    """Update the display with new weather data"""
    # Create a new image with white background
    Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
    draw = ImageDraw.Draw(Himage)
    
    # Load fonts of different sizes
    try:
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Weather section (top right)
    weather_icon = WEATHER_ICONS.get(weather_data['description'], '?')
    temp_text = f"{weather_data['temperature']}°"
    
    # Draw weather info in top right
    draw.text((Himage.width - 75, 8), f"{weather_icon}", font=font_medium, fill=epd.BLACK)
    draw.text((Himage.width - 45, 8), f"{temp_text}", font=font_medium, fill=epd.BLACK)

    # Draw bus information
    y_position = 15
    for bus in bus_data:
        # Draw bus line number
        draw.text((10, y_position), f"{bus['line']}", font=font_large, fill=epd.BLACK)
        # Draw arrow
        draw.text((55, y_position + 3), "→", font=font_medium, fill=epd.BLACK)
        # Draw waiting times
        times_text = ", ".join(bus["times"])
        draw.text((85, y_position + 5), times_text, font=font_medium, fill=epd.BLACK)
        y_position += 45

    # If there's an error message, display it
    if error_message:
        # Draw error message in red (if available) or black
        error_bbox = draw.textbbox((0, 0), error_message, font=font_small)
        error_width = error_bbox[2] - error_bbox[0]
        error_x = (Himage.width - error_width) // 2
        draw.text((error_x, Himage.height - 40), 
                 error_message, font=font_small, fill=epd.RED if hasattr(epd, 'RED') else epd.BLACK)

    # Add current time in bottom right
    current_time = time.strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    draw.text((Himage.width - time_width - 5, Himage.height - 20), 
              current_time, font=font_small, fill=epd.BLACK)

    # Draw a border around the display
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=epd.BLACK)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(90, expand=True)
    
    # Convert image to buffer
    buffer = epd.getbuffer(Himage)
    
    # Always use display(), the speed difference comes from init_Fast()
    epd.display(buffer)

def main():
    epd = None
    try:
        logging.info("E-ink Display Starting")
        
        # Initialize services
        weather = WeatherService()
        bus = BusService()
        
        # Initialize the display once at startup
        epd = epd2in13g_V2.EPD()   
        epd.init()
        epd.Clear()
        logging.info("Display initialized")
        
        # Initialize fast mode for updates
        epd.init_Fast()
        logging.info("Fast mode initialized")
        
        # Counter for full refresh every hour
        update_count = 0
        FULL_REFRESH_INTERVAL = 60  # Number of updates before doing a full refresh
        
        # Main loop
        while True:
            try:
                # Get data
                weather_data = weather.get_weather()
                bus_data, error_message = bus.get_waiting_times()
                
                # Check if we need a full refresh (every FULL_REFRESH_INTERVAL updates)
                needs_full_refresh = update_count >= FULL_REFRESH_INTERVAL
                
                if needs_full_refresh:
                    logging.info("Performing hourly full refresh...")
                    epd.init()
                    epd.Clear()
                    epd.init_Fast()
                    update_count = 0
                
                # Update the display
                update_display(epd, weather_data, bus_data, error_message)
                
                # If there was an error, wait less time before retry
                wait_time = 60 if not error_message else 10
                
                # Log next refresh type
                updates_until_refresh = FULL_REFRESH_INTERVAL - update_count - 1
                next_update = f"full refresh" if updates_until_refresh == 0 else f"fast refresh ({updates_until_refresh} until full refresh)"
                logging.info(f"Waiting {wait_time} seconds until next update ({next_update})")
                time.sleep(wait_time)
                
                # Only increment counter if there was no error
                if not error_message:
                    update_count += 1
                
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(10)
                continue
            
    except KeyboardInterrupt:
        logging.info("Ctrl+C pressed - Cleaning up...")
        
    except Exception as e:
        logging.error(f"Main error: {e}")
        
    finally:
        logging.info("Cleaning up...")
        if epd is not None:
            try:
                # Final cleanup with full initialization
                epd.init()
                epd.Clear()
                epd.sleep()
                epd2in13g_V2.epdconfig.module_exit(cleanup=True)
                logging.info("Display cleanup completed")
            except Exception as e:
                logging.error(f"Error during cleanup: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
