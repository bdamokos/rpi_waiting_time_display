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

def draw_dithered_box(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Draw a box with dithered background and centered text"""
    logging.debug(f"Drawing dithered box with colors: {primary_color} ({ratio:.2f}) and {secondary_color} ({1-ratio:.2f})")
    
    # Map color names to epd colors
    color_map = {
        'black': epd.BLACK,
        'red': epd.RED,
        'yellow': epd.YELLOW,
        'white': epd.WHITE
    }
    
    primary = color_map[primary_color]
    secondary = color_map[secondary_color]
    
    # Create dithering pattern using a smaller repeating pattern
    pattern_size = 4  # Use 4x4 pattern for more even distribution
    for i in range(width):
        for j in range(height):
            # Use pattern coordinates instead of simple checkerboard
            pattern_x = i % pattern_size
            pattern_y = j % pattern_size
            pattern_value = (pattern_x * pattern_size + pattern_y) / (pattern_size * pattern_size)
            use_primary = pattern_value < ratio
            
            pixel_color = primary if use_primary else secondary
            draw.point((x + i, y + j), fill=pixel_color)
    
    # Draw border in primary color
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=primary)
    
    # Calculate text position to center it
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    text_x = x + (width - text_width) // 2
    text_y = y + (height - text_height) // 2
    
    # Draw text in contrasting color
    text_color = epd.BLACK if primary_color == 'white' and secondary_color == 'white' else epd.WHITE
    draw.text((text_x, text_y), text, font=font, fill=text_color)

def update_display(epd, weather_data, bus_data, error_message=None, stop_name=None, first_run=False):
    """Update the display with new weather data"""
    logging.info(f"Display dimensions: {epd.height}x{epd.width} (height x width)")
    
    # Create a new image with white background
    Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
    draw = ImageDraw.Draw(Himage)
    
    # Load fonts
    try:
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Calculate layout
    MARGIN = 8  # Space at top and bottom
    HEADER_HEIGHT = 20  # Height for stop name and weather
    BOX_HEIGHT = 40  # Height of bus line boxes
    SPACING = (epd.width - (2 * MARGIN) - HEADER_HEIGHT - (2 * BOX_HEIGHT)) // 2  # Equal spacing between elements

    # Draw stop name in top left and weather in top right
    if stop_name:
        draw.text((MARGIN, MARGIN), stop_name, font=font_small, fill=epd.BLACK)

    weather_icon = WEATHER_ICONS.get(weather_data['description'], '?')
    temp_text = f"{weather_data['temperature']}°"
    weather_text = f"{weather_icon} {temp_text}"
    weather_bbox = draw.textbbox((0, 0), weather_text, font=font_small)
    weather_width = weather_bbox[2] - weather_bbox[0]
    draw.text((Himage.width - weather_width - MARGIN, MARGIN), 
              weather_text, font=font_small, fill=epd.BLACK)

    # Calculate Y positions for bus info
    first_box_y = MARGIN + HEADER_HEIGHT + SPACING
    second_box_y = first_box_y + BOX_HEIGHT + SPACING

    # Draw bus information
    for idx, bus in enumerate(bus_data):
        y_position = first_box_y if idx == 0 else second_box_y
        
        # Draw dithered box with line number
        primary_color, secondary_color, ratio = bus['colors']
        draw_dithered_box(
            draw=draw,
            epd=epd,
            x=10,
            y=y_position,
            width=45,
            height=BOX_HEIGHT,
            text=bus['line'],
            primary_color=primary_color,
            secondary_color=secondary_color,
            ratio=ratio,
            font=font_large
        )
        
        # Draw arrow and times
        draw.text((65, y_position + (BOX_HEIGHT - 24) // 2), "→", 
                  font=font_medium, fill=epd.BLACK)
        times_text = ", ".join(bus["times"])
        draw.text((95, y_position + (BOX_HEIGHT - 24) // 2), times_text, 
                  font=font_medium, fill=epd.BLACK)

    # Draw current time aligned with bottom of second box
    current_time = time.strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    time_height = time_bbox[3] - time_bbox[1]
    draw.text((Himage.width - time_width - MARGIN, 
               second_box_y + BOX_HEIGHT - time_height), 
              current_time, font=font_small, fill=epd.BLACK)

    # Draw error message if present
    if error_message:
        error_bbox = draw.textbbox((0, 0), error_message, font=font_small)
        error_width = error_bbox[2] - error_bbox[0]
        error_x = (Himage.width - error_width) // 2
        draw.text((error_x, second_box_y + BOX_HEIGHT + MARGIN), 
                 error_message, font=font_small, fill=epd.RED)

    # Draw a border around the display
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=epd.BLACK)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(90, expand=True)
    
    # Convert image to buffer
    buffer = epd.getbuffer(Himage)
    
    # Add debug log before display command
    logging.debug("About to call epd.display() with new buffer")
    epd.display(buffer)

def main():
    epd = None
    try:
        logging.info("E-ink Display Starting")
        
        # Initialize services
        weather = WeatherService()
        bus = BusService()
        
        # Add debug logs before EPD commands
        logging.debug("About to initialize EPD")
        epd = epd2in13g_V2.EPD()   
        
        logging.debug("About to call epd.init()")
        epd.init()
        
        logging.debug("About to call epd.Clear()")
        epd.Clear()
        logging.info("Display initialized")
        
        logging.debug("About to call epd.init_Fast()")
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
                bus_data, error_message, stop_name = bus.get_waiting_times()
                
                # Check if we need a full refresh (every FULL_REFRESH_INTERVAL updates)
                needs_full_refresh = update_count >= FULL_REFRESH_INTERVAL
                
                if needs_full_refresh:
                    logging.info("Performing hourly full refresh...")
                    logging.debug("About to call epd.init()")
                    epd.init()
                    logging.debug("About to call epd.Clear()")
                    epd.Clear()
                    logging.debug("About to call epd.init_Fast()")
                    epd.init_Fast()
                    update_count = 0
                
                # Update the display
                update_display(epd, weather_data, bus_data, error_message, stop_name)
                
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
                logging.debug("About to call final epd.init()")
                epd.init()
                logging.debug("About to call final epd.Clear()")
                epd.Clear()
                logging.debug("About to call epd.sleep()")
                epd.sleep()
                logging.debug("About to call module_exit")
                epd2in13g_V2.epdconfig.module_exit(cleanup=True)
                logging.info("Display cleanup completed")
            except Exception as e:
                logging.error(f"Error during cleanup: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
