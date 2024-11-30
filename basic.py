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
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from weather import WeatherService
from bus_service import BusService
from dithering import draw_dithered_box
import qrcode
from io import BytesIO

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

def update_display(epd, weather_data, bus_data, error_message=None, stop_name=None, first_run=False):
    """Update the display with new weather data"""
    logging.info(f"Display dimensions: {epd.height}x{epd.width} (height x width)")
    
    # Create a new image with white background
    Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
    draw = ImageDraw.Draw(Himage)
    
    try:
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
    except:
        font_large = ImageFont.load_default()
        font_medium = font_small = font_large

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
    logging.debug("About to call epd.display() with new buffer")
    epd.display(buffer)

def draw_weather_display(epd, weather_data):
    """Draw a weather-focused display when no bus times are available"""
    # Create a new image with white background
    Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
    draw = ImageDraw.Draw(Himage)
    
    try:
        font_xl = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
    except:
        font_xl = ImageFont.load_default()
        font_large = font_medium = font_small = font_xl

    # Draw current time
    current_time = datetime.now().strftime("%H:%M")
    draw.text((10, 5), current_time, font=font_large, fill=epd.BLACK)

    # Draw current temperature (large)
    temp_text = f"{weather_data['current']['temperature']}°C"
    draw.text((10, 45), temp_text, font=font_xl, fill=epd.BLACK)

    # Draw weather icon
    weather_icon = WEATHER_ICONS.get(weather_data['current']['description'], '?')
    draw.text((120, 45), weather_icon, font=font_xl, fill=epd.BLACK)

    # Draw additional weather info
    y_pos = 100
    info_text = [
        f"Feels like: {weather_data['feels_like']}°C",
        f"Humidity: {weather_data['humidity']}%",
        f"Wind: {weather_data['wind_speed']} km/h",
        f"Rain: {weather_data['precipitation_chance']}%"
    ]
    
    for text in info_text:
        draw.text((10, y_pos), text, font=font_small, fill=epd.BLACK)
        y_pos += 20

    # Draw next hours forecast
    y_pos = 180
    draw.text((10, y_pos), "Next hours:", font=font_small, fill=epd.BLACK)
    y_pos += 20
    
    for forecast in weather_data['forecast']:
        text = f"{forecast['time']}: {forecast['temp']}°C"
        draw.text((10, y_pos), text, font=font_small, fill=epd.BLACK)
        y_pos += 20

    # Generate and draw QR code
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    qr.add_data('http://raspberrypi.local:5001')
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert PIL image to RGB
    qr_img = qr_img.convert('RGB')
    
    # Calculate position for QR code (bottom right corner)
    qr_size = qr_img.size[0]
    qr_x = Himage.width - qr_size - 10
    qr_y = Himage.height - qr_size - 10
    
    # Paste QR code onto main image
    Himage.paste(qr_img, (qr_x, qr_y))

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
                weather_data = weather.get_detailed_weather()
                bus_data, error_message, stop_name = bus.get_waiting_times()
                
                # Filter out bus lines with no valid times
                valid_bus_data = [
                    bus for bus in bus_data 
                    if any(time != "--" for time in bus["times"])
                ]
                
                # Determine display mode
                if valid_bus_data:
                    # Update display with only the valid bus lines
                    update_display(epd, weather_data['current'], valid_bus_data, error_message, stop_name)
                else:
                    draw_weather_display(epd, weather_data)
                
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
