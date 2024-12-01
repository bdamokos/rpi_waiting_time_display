#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
# picdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'pic')
# libdir = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), 'lib')
# if os.path.exists(libdir):
#     sys.path.append(libdir)

import logging
from display_adapter import DisplayAdapter
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from weather import WeatherService
from bus_service import BusService
from dithering import draw_dithered_box
import qrcode
from io import BytesIO
import importlib
import log_config

logger = logging.getLogger(__name__)

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

def update_display(epd, weather_data, bus_data, error_message=None, stop_name=None, first_run=False):
    """Update the display with new weather data"""
    logger.info(f"Display dimensions: {epd.height}x{epd.width} (height x width)")
    
    # Create a new image with white background
    Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
    draw = ImageDraw.Draw(Himage)
    
    try:
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
        logger.info(f"Found DejaVu fonts: {font_large}, {font_medium}, {font_small}")
    except:
        font_large = ImageFont.load_default()
        font_medium = font_small = font_large
        logger.info(f"No DejaVu fonts found, using default: {font_large}, {font_medium}, {font_small}")

    # Calculate layout
    MARGIN = 8
    HEADER_HEIGHT = 20
    BOX_HEIGHT = 40
    
    # Adjust spacing based on number of bus lines
    if len(bus_data) == 1:
        # Center the single bus line vertically
        first_box_y = (epd.width - HEADER_HEIGHT - BOX_HEIGHT) // 2
        second_box_y = first_box_y  # Not used but kept for consistency
    else:
        # Original spacing for two lines
        SPACING = (epd.width - (2 * MARGIN) - HEADER_HEIGHT - (2 * BOX_HEIGHT)) // 2
        first_box_y = MARGIN + HEADER_HEIGHT + SPACING
        second_box_y = first_box_y + BOX_HEIGHT + SPACING

    # Draw stop name and weather (rest of the header remains the same)
    if stop_name:
        draw.text((MARGIN, MARGIN), stop_name, font=font_small, fill=epd.BLACK)

    weather_icon = WEATHER_ICONS.get(weather_data['description'], '?')
    temp_text = f"{weather_data['temperature']}°"
    weather_text = f"{weather_icon} {temp_text}"
    weather_bbox = draw.textbbox((0, 0), weather_text, font=font_small)
    weather_width = weather_bbox[2] - weather_bbox[0]
    draw.text((Himage.width - weather_width - MARGIN, MARGIN), 
              weather_text, font=font_small, fill=epd.BLACK)

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
        
        # Draw arrow
        draw.text((65, y_position + (BOX_HEIGHT - 24) // 2), "→", 
                  font=font_medium, fill=epd.BLACK)

        # Process times and messages
        times = bus["times"]
        messages = bus.get("messages", [None] * len(times))
        
        x_pos = 95
        y_pos = y_position + (BOX_HEIGHT - 24) // 2
        
        # Handle different message cases
        if messages and messages[0] == "End of service":
            # Display end of service message
            draw.text((x_pos, y_pos), "End of service", 
                     font=font_medium, fill=epd.BLACK)
        else:
            # Display times with potential messages
            max_width = Himage.width - x_pos - MARGIN  # Available width
            times_shown = 0
            
            for time, message in zip(times, messages):
                # Calculate width needed for this time + message
                time_bbox = draw.textbbox((0, 0), time, font=font_medium)
                time_width = time_bbox[2] - time_bbox[0]
                
                message_width = 0
                if message:
                    if message == "Last":
                        msg_text = "Last departure"
                    elif message == "theor.":
                        msg_text = "(theor.)"
                    msg_bbox = draw.textbbox((0, 0), msg_text, font=font_small)
                    message_width = msg_bbox[2] - msg_bbox[0] + 5  # 5px spacing
                
                # Check if we have space for this time + message + spacing
                if x_pos + time_width + message_width + 30 > Himage.width - MARGIN:
                    break
                
                # Draw time
                draw.text((x_pos, y_pos), time, font=font_medium, fill=epd.BLACK)
                
                # Draw message if present
                if message:
                    msg_x = x_pos + time_width + 5
                    if message == "Last":
                        draw.text((msg_x, y_pos + 5), "Last departure", 
                                font=font_small, fill=epd.BLACK)
                        break  # Don't show more times after "Last departure"
                    elif message == "theor.":
                        draw.text((msg_x, y_pos + 5), "(theor.)", 
                                font=font_small, fill=epd.BLACK)
                
                # Move x position for next time
                x_pos += time_width + message_width + 30  # Add spacing between times
                times_shown += 1

    # Draw current time at the bottom
    current_time = datetime.now().strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    time_height = time_bbox[3] - time_bbox[1]
    
    # Adjust time position based on number of bus lines
    if len(bus_data) == 1:
        time_y = first_box_y + BOX_HEIGHT + MARGIN
    else:
        time_y = second_box_y + BOX_HEIGHT - time_height
    
    draw.text((Himage.width - time_width - MARGIN, time_y), 
              current_time, font=font_small, fill=epd.BLACK)

    # Draw error message if present
    if error_message:
        error_bbox = draw.textbbox((0, 0), error_message, font=font_small)
        error_width = error_bbox[2] - error_bbox[0]
        error_x = (Himage.width - error_width) // 2
        error_y = time_y + time_height + MARGIN if len(bus_data) == 1 else second_box_y + BOX_HEIGHT + MARGIN
        draw.text((error_x, error_y), error_message, font=font_small, fill=epd.RED)

    # Draw a border around the display
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=epd.BLACK)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(90, expand=True)
    
    # Convert image to buffer
    buffer = epd.getbuffer(Himage)
    
    # Add debug log before display command
    logger.debug("About to call epd.display() with new buffer")
    epd.display(buffer)

def draw_weather_display(epd, weather_data, last_weather_data=None):
    """Draw a weather-focused display when no bus times are available"""
    # Create a new image with white background
    Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)  # 250x120 width x height
    draw = ImageDraw.Draw(Himage)
    
    try:
        font_xl = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 42)
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 28)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 20)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
    except:
        font_xl = ImageFont.load_default()
        font_large = font_medium = font_small = font_xl

    MARGIN = 8
    
    # Top row: Large temperature and weather icon
    temp_text = f"{weather_data['current']['temperature']}°C"
    weather_icon = WEATHER_ICONS.get(weather_data['current']['description'], '?')
    
    # Center temperature and icon
    temp_bbox = draw.textbbox((0, 0), temp_text, font=font_xl)
    temp_width = temp_bbox[2] - temp_bbox[0]
    icon_bbox = draw.textbbox((0, 0), weather_icon, font=font_xl)
    icon_width = icon_bbox[2] - icon_bbox[0]
    
    total_width = temp_width + icon_width + 20
    start_x = (Himage.width - total_width) // 2
    
    draw.text((start_x, MARGIN), temp_text, font=font_xl, fill=epd.BLACK)
    draw.text((start_x + temp_width + 20, MARGIN), weather_icon, font=font_xl, fill=epd.BLACK)

    # Middle row: Next sun event and air quality
    y_pos = 55
    
    # Show either sunrise or sunset based on time of day
    if weather_data['is_daytime']:
        sun_text = f"{weather_data['sunset']}"
        sun_icon = "🌅"
    else:
        sun_text = f"{weather_data['sunrise']}"
        sun_icon = "🌄"
    
    # Add AQI if available
    if weather_data.get('air_quality'):
        aqi_text = f"AQI: {weather_data['air_quality']['aqi']} ({weather_data['air_quality']['aqi_label']})"
        
        # Draw sun info and AQI on same line
        sun_full = f"{sun_icon} {sun_text}"
        sun_bbox = draw.textbbox((0, 0), sun_full, font=font_large)
        aqi_bbox = draw.textbbox((0, 0), aqi_text, font=font_medium)
        
        # Calculate positions to center both pieces of text
        total_width = sun_bbox[2] - sun_bbox[0] + 30 + (aqi_bbox[2] - aqi_bbox[0])  # 30px spacing
        start_x = (Himage.width - total_width) // 2
        
        draw.text((start_x, y_pos), sun_full, font=font_large, fill=epd.BLACK)
        draw.text((start_x + (sun_bbox[2] - sun_bbox[0]) + 30, y_pos + 5), aqi_text, font=font_medium, fill=epd.BLACK)
    else:
        # Center sun information only
        sun_bbox = draw.textbbox((0, 0), f"{sun_icon} {sun_text}", font=font_large)
        sun_width = sun_bbox[2] - sun_bbox[0]
        sun_x = (Himage.width - sun_width) // 2
        draw.text((sun_x, y_pos), f"{sun_icon} {sun_text}", font=font_large, fill=epd.BLACK)

    # Bottom row: Tomorrow's forecast
    y_pos = 90
    tomorrow_text = f"Tomorrow: {weather_data['tomorrow']['min']}°C to {weather_data['tomorrow']['max']}°C"
    tomorrow_bbox = draw.textbbox((0, 0), tomorrow_text, font=font_medium)
    tomorrow_width = tomorrow_bbox[2] - tomorrow_bbox[0]
    tomorrow_x = (Himage.width - tomorrow_width) // 2
    draw.text((tomorrow_x, y_pos), tomorrow_text, font=font_medium, fill=epd.BLACK)

    # Generate and draw QR code (larger size)
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    qr.add_data('http://raspberrypi.local:5001')
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')
    
    # Scale QR code to larger size
    qr_size = 45
    qr_img = qr_img.resize((qr_size, qr_size))
    qr_x = Himage.width - qr_size - MARGIN
    qr_y = MARGIN
    Himage.paste(qr_img, (qr_x, qr_y))

    # Draw time under QR code
    current_time = datetime.now().strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    draw.text((qr_x + (qr_size - time_width)//2, qr_y + qr_size + 2), 
              current_time, font=font_small, fill=epd.BLACK)

    # Draw a border around the display
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=epd.BLACK)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(90, expand=True)
    
    # Display the image
    buffer = epd.getbuffer(Himage)
    epd.display(buffer)

def main():
    epd = None
    try:
        logger.info("E-ink Display Starting")
        
        # Initialize services
        weather = WeatherService()
        bus = BusService()
        
        # Initialize display using adapter
        logger.debug("About to initialize display")
        epd = DisplayAdapter.get_display()
        
        # Add debug logs before EPD commands
        logger.debug("About to call epd.init()")
        epd.init()
        
        logger.debug("About to call epd.Clear()")
        epd.Clear()
        logger.info("Display initialized")
        
        logger.debug("About to call epd.init_Fast()")
        epd.init_Fast()
        logger.info("Fast mode initialized")
        
        # Counter for full refresh every hour
        update_count = 0
        FULL_REFRESH_INTERVAL = 60  # Number of updates before doing a full refresh
        
        # Add variables for weather display
        last_weather_data = None
        last_weather_update = datetime.now()
        WEATHER_UPDATE_INTERVAL = 600  # 10 minutes in seconds
        in_weather_mode = False  # Track which mode we're in
        
        # Main loop
        while True:
            try:
                # Get data
                weather_data = weather.get_detailed_weather()
                bus_data, error_message, stop_name = bus.get_waiting_times()
                
                # Filter out bus lines with no valid times
                valid_bus_data = [
                    bus for bus in bus_data 
                    if any(time != "--" for time in bus["times"])
                ]
                
                current_time = datetime.now()
                
                # Determine if we need a full refresh
                needs_full_refresh = update_count >= FULL_REFRESH_INTERVAL
                
                if needs_full_refresh:
                    logger.info("Performing hourly full refresh...")
                    logger.debug("About to call epd.init()")
                    epd.init()
                    logger.debug("About to call epd.Clear()")
                    epd.Clear()
                    logger.debug("About to call epd.init_Fast()")
                    epd.init_Fast()
                    update_count = 0
                
                # Determine display mode
                if valid_bus_data:
                    # Bus display mode
                    in_weather_mode = False
                    last_weather_data = None  # Reset weather tracking
                    last_weather_update = current_time
                    update_display(epd, weather_data['current'], valid_bus_data, error_message, stop_name)
                    wait_time = 60 if not error_message else 10
                    update_count += 1
                else:
                    # Weather display mode
                    in_weather_mode = True
                    weather_changed = (
                        last_weather_data is None or
                        weather_data['current'] != last_weather_data['current'] or
                        weather_data['forecast'] != last_weather_data['forecast']
                    )
                    
                    time_since_update = (current_time - last_weather_update).total_seconds()
                    
                    # Always display on first run (when last_weather_data is None)
                    if (last_weather_data is None or 
                        (weather_changed and time_since_update >= WEATHER_UPDATE_INTERVAL) or 
                        time_since_update >= 3600):
                        draw_weather_display(epd, weather_data)
                        last_weather_data = weather_data
                        last_weather_update = current_time
                    
                    # In weather mode, we wait longer between checks
                    wait_time = WEATHER_UPDATE_INTERVAL
                
                # Log next update info
                if in_weather_mode:
                    next_update = f"weather update in {wait_time} seconds"
                else:
                    updates_until_refresh = FULL_REFRESH_INTERVAL - update_count - 1
                    next_update = f"bus update in {wait_time} seconds ({updates_until_refresh} until full refresh)"
                
                logger.info(f"Waiting {wait_time} seconds until next update ({next_update})")
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(10)
                continue
            
    except KeyboardInterrupt:
        logger.info("Ctrl+C pressed - Cleaning up...")
        
    except Exception as e:
        logger.error(f"Main error: {e}")
        
    finally:
        logger.info("Cleaning up...")
        if epd is not None:
            try:
                logger.debug("About to call final epd.init()")
                epd.init()
                logger.debug("About to call final epd.Clear()")
                epd.Clear()
                logger.debug("About to call epd.sleep()")
                epd.sleep()
                logger.debug("About to call module_exit")
                epd.epdconfig.module_exit(cleanup=True)
                logger.info("Display cleanup completed")
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
        sys.exit(0)

if __name__ == "__main__":
    main()
