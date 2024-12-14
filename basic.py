#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
from pathlib import Path
import logging
from display_adapter import DisplayAdapter
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from font_utils import get_font_paths
from weather import WeatherService, get_weather_icon
from bus_service import BusService
from dithering import draw_dithered_box
import qrcode
import importlib
import log_config
import random
import traceback
from debug_server import start_debug_server
from wifi_manager import is_connected, show_no_wifi_display, get_hostname
import subprocess
import threading
import math
from flights import gather_flights_within_radius, enhance_flight_data
from threading import Lock
logger = logging.getLogger(__name__)
# Set logging level for PIL.PngImagePlugin and urllib3.connectionpool to warning
logging.getLogger('PIL.PngImagePlugin').setLevel(logging.WARNING)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)


display_lock = Lock()  # Global lock for display operations

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

# Add to top of file with other constants

CURRENT_ICON_SIZE = (46, 46)  # Size for current weather icon
FORECAST_ICON_SIZE = (28, 28)  # Smaller size for forecast icons


DISPLAY_REFRESH_INTERVAL = int(os.getenv("refresh_interval", 90))
DISPLAY_REFRESH_MINIMAL_TIME = int(os.getenv("refresh_minimal_time", 30))
DISPLAY_REFRESH_FULL_INTERVAL = int(os.getenv("refresh_full_interval", 3600))
DISPLAY_REFRESH_WEATHER_INTERVAL = int(os.getenv("refresh_weather_interval", 600))

weather_enabled = True if os.getenv("OPENWEATHER_API_KEY") else False

HOTSPOT_ENABLED = os.getenv('hotspot_enabled', 'true').lower() == 'true'
hostname = get_hostname()
HOTSPOT_SSID = os.getenv('hotspot_ssid', f'PiHotspot-{hostname}')
HOTSPOT_PASSWORD = os.getenv('hotspot_password', 'YourPassword')

DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))

COORDINATES_LAT = float(os.getenv('Coordinates_LAT'))
COORDINATES_LNG = float(os.getenv('Coordinates_LNG'))
flights_enabled = True if os.getenv('flights_enabled', 'false').lower() == 'true' else False
aeroapi_enabled = True if os.getenv('aeroapi_enabled', 'false').lower() == 'true' else False
flight_check_interval = int(os.getenv('flight_check_interval', 10))
FLIGHT_MAX_RADIUS = int(os.getenv('flight_max_radius', 3))
flight_altitude_convert_feet = True if os.getenv('flight_altitude_convert_feet', 'false').lower() == 'true' else False
if not weather_enabled:
    logger.warning("Weather is not enabled, weather data will not be displayed. Please set OPENWEATHER_API_KEY in .env to enable it.")

def update_display(epd, weather_data=None, bus_data=None, error_message=None, stop_name=None, first_run=False):
    """Update the display with new weather and waiting timesdata"""
    MARGIN = 8

    # Handle different color definitions
    BLACK = epd.BLACK
    WHITE = epd.WHITE
    RED = getattr(epd, 'RED', BLACK)  # Fall back to BLACK if RED not available
    YELLOW = getattr(epd, 'YELLOW', BLACK)  # Fall back to BLACK if YELLOW not available

    logger.info(f"Display dimensions: {epd.height}x{epd.width} (height x width)")
    
    # Create a new image with white background
    if epd.is_bw_display:
        Himage = Image.new('1', (epd.height, epd.width), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (epd.height, epd.width), WHITE)
    draw = ImageDraw.Draw(Himage)
    
    try:
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 32)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)

        # logger.info(f"Found DejaVu fonts: {font_large}, {font_medium}, {font_small}")
    except:
        font_large = ImageFont.load_default()
        font_medium = font_small = font_large
        logger.warning(f"No DejaVu fonts found, using default: {font_large}, {font_medium}, {font_small}. Install DeJaVu fonts with \n sudo apt install fonts-dejavu\n")
    try:
        emoji_font = ImageFont.truetype('/usr/local/share/fonts/noto/NotoEmoji-Regular.ttf', 16)
        emoji_font_medium = ImageFont.truetype('/usr/local/share/fonts/noto/NotoEmoji-Regular.ttf', 20)
    except:
        emoji_font = font_small
        emoji_font_medium = font_medium
        logger.warning(f"No Noto Emoji font found, using {emoji_font.getname()} instead.")
    if not weather_enabled:
        weather_data = None
        logger.warning("Weather is not enabled, weather data will not be displayed. Do not forget to set OPENWEATHER_API_KEY in .env to enable it.")
    if weather_enabled:
        weather_icon = WEATHER_ICONS.get(weather_data['description'], '')
        logger.debug(f"Weather icon: {weather_icon}, description: {weather_data['description']}, font: {emoji_font.getname()}")
        temp_text = f"{weather_data['temperature']}°"
        
        weather_text = f"{temp_text}"
        weather_icon_bbox = draw.textbbox((0, 0), weather_icon, font=emoji_font)
        weather_icon_width = weather_icon_bbox[2] - weather_icon_bbox[0]
        weather_bbox = draw.textbbox((0, 0), weather_text, font=font_small)
        weather_text_width = weather_bbox[2] - weather_bbox[0]
        weather_width = weather_text_width + weather_icon_width
        draw.text((Himage.width - weather_width - weather_icon_width - MARGIN, MARGIN), weather_icon, font=emoji_font, fill=BLACK)
        draw.text((Himage.width - weather_width - MARGIN, MARGIN), weather_text, font=font_small, fill=BLACK)
    stop_name_height = 0
    if stop_name:
        stop_name_bbox = draw.textbbox((0, 0), stop_name, font=font_small)
        stop_name_width = stop_name_bbox[2] - stop_name_bbox[0]
        if (weather_enabled and (Himage.width - weather_width - stop_name_width - MARGIN) < 0) or (not weather_enabled and (Himage.width - stop_name_width - MARGIN) < 0):
            logger.debug(f"Stop name width: {stop_name_width}, weather width: {weather_width if weather_enabled else 0}, total width: {Himage.width}, margin: {MARGIN}. The total width is too small for the stop name and weather.")
            # Split stop name into two lines
            stop_name_parts = stop_name.split(' ', 1)
            logger.debug(f"Stop name parts: {stop_name_parts}")
            if len(stop_name_parts) > 1:
                line1, line2 = stop_name_parts
            else:
                line1 = stop_name
                line2 = ""
            
            # Draw first line
            draw.text((MARGIN, MARGIN), line1, font=font_small, fill=BLACK)
            line1_bbox = draw.textbbox((0, 0), line1, font=font_small)
            stop_name_height = line1_bbox[3] - line1_bbox[1] + MARGIN
            
            
            # Draw second line if it exists
            if line2:
                line1_bbox = draw.textbbox((0, 0), line1, font=font_small)
                line1_height = line1_bbox[3] - line1_bbox[1]
                draw.text((MARGIN, MARGIN + line1_height+MARGIN), line2, font=font_small, fill=BLACK)
                line2_bbox = draw.textbbox((0, 0), line2, font=font_small)
                line2_height = line2_bbox[3] - line2_bbox[1]
                stop_name_height = line1_height + line2_height + MARGIN + MARGIN + MARGIN
                logger.debug(f"Stop name height: {stop_name_height}")
        else:
            logger.debug(f"Stop name width: {stop_name_width}, weather width: {weather_width if weather_enabled else 0}, total width: {Himage.width}, margin: {MARGIN}")
            draw.text((MARGIN, MARGIN), stop_name, font=font_small, fill=BLACK)
            stop_name_bbox = draw.textbbox((0, 0), stop_name, font=font_small)
            stop_name_height = stop_name_bbox[3] - stop_name_bbox[1] + MARGIN
    logger.debug(f"Stop name height: {stop_name_height}")
    # Calculate layout

    HEADER_HEIGHT = stop_name_height + MARGIN
    BOX_HEIGHT = 40
    
    # Adjust spacing based on number of bus lines
    if len(bus_data) == 1:
        # Center the single bus line vertically
        first_box_y = MARGIN + HEADER_HEIGHT + ((Himage.height - HEADER_HEIGHT - BOX_HEIGHT - stop_name_height) // 2)
        logger.debug(f"First box y: {first_box_y}. Header height: {HEADER_HEIGHT}, box height: {BOX_HEIGHT}. Himage height: {Himage.height}")
        second_box_y = first_box_y  # Not used but kept for consistency
    elif len(bus_data) == 2:
        # Calculate spacing for two lines to be evenly distributed
        total_available_height = Himage.height - HEADER_HEIGHT - (2 * BOX_HEIGHT)
        SPACING = total_available_height // 3  # Divide remaining space into thirds
        
        first_box_y = HEADER_HEIGHT + SPACING
        second_box_y = first_box_y + BOX_HEIGHT + SPACING
        
        logger.debug(f"Two-line layout: Header height: {HEADER_HEIGHT}, Available height: {total_available_height}")
        logger.debug(f"Spacing: {SPACING}, First box y: {first_box_y}, Second box y: {second_box_y}")
    else:
        logger.error(f"Unexpected number of bus lines: {len(bus_data)}. Display currently supports up to 2 lines from the same provider and stop.")
        draw.text((MARGIN, MARGIN), "Error, see logs", font=font_large, fill=RED)
        return






    # Draw bus information
    for idx, bus in enumerate(bus_data):
        y_position = first_box_y if idx == 0 else second_box_y
        
        # Draw dithered box with line number
        primary_color, secondary_color, ratio = bus['colors']
        line_text_length = len(bus['line'])
        line_text_width = 35 + (line_text_length * 9)
        stop_name_bbox = draw_dithered_box(
            draw=draw,
            epd=epd,
            x=10,
            y=y_position,
            width=line_text_width,
            height=BOX_HEIGHT,
            text=bus['line'],
            primary_color=primary_color,
            secondary_color=secondary_color,
            ratio=ratio,
            font=font_large
        )
        

        # Draw arrow
        draw.text((line_text_width + MARGIN+10, y_position + (BOX_HEIGHT - 24) // 2), "→", 
                  font=font_medium, fill=BLACK)
        # Calculate width of arrow
        arrow_bbox = draw.textbbox((0, 0), "→", font=font_medium)
        arrow_width = arrow_bbox[2] - arrow_bbox[0] + MARGIN

        # Process times and messages
        times = bus["times"]
        messages = bus.get("messages", [None] * len(times))
        
        x_pos = line_text_width + arrow_width + MARGIN + MARGIN
        y_pos = y_position + (BOX_HEIGHT - 24) // 2
        
        # Calculate maximum available width
        max_width = Himage.width - x_pos - MARGIN - MARGIN  # Available width
        times_shown = 0
        len_times = len(times)
        if len_times <=2:
            EXTRA_SPACING = 10
        else:
            EXTRA_SPACING = 0
        for time, message in zip(times, messages):
            if not time.lower().endswith("'"):
                time = str(time) + "'"
            if time.lower()=="0'" or time.lower()=="0":
                time = "↓↓"
            # Calculate width needed for this time + message
            time_bbox = draw.textbbox((0, 0), time, font=font_medium)
            time_width = time_bbox[2] - time_bbox[0]
            

            message_width = 0
            if message:
                if message == "Last":
                    msg_text = "Last departure"
                elif message == "theor.":
                    msg_text = "(theor.)"
                elif message:
                    msg_text = message
                msg_bbox = draw.textbbox((0, 0), msg_text, font=font_small)
                message_width = msg_bbox[2] - msg_bbox[0] + 5  # 5px spacing
            
            # Check if we have space for this time + message + spacing
            if times_shown > 0 and (time_width + message_width + MARGIN + EXTRA_SPACING > max_width):
                break
            
            # Check if there is an emoji to show
            if '🕒' in time or '⚡' in time:
                emoji_text = '🕒' if '🕒' in time else '⚡'
                emoji_bbox = draw.textbbox((0, 0), emoji_text, font=emoji_font)
                emoji_width = emoji_bbox[2] - emoji_bbox[0]
                time_text = time.replace('🕒', '').replace('⚡', '')
                time_bbox = draw.textbbox((0, 0), time_text, font=font_medium)
                time_text_width = time_bbox[2] - time_bbox[0]
                time_width = time_text_width + emoji_width
                draw.text((x_pos + MARGIN - 2, y_pos + 2), emoji_text, font=emoji_font_medium, fill=BLACK)
                draw.text((x_pos + MARGIN + emoji_width, y_pos ), time_text, font=font_medium, fill=BLACK)
            else:
                draw.text((x_pos + MARGIN, y_pos), time, font=font_medium, fill=BLACK)


            
            # Draw message if present
            if message:
                msg_x = x_pos + time_width + MARGIN
                if message == "Last":
                    draw.text((msg_x, y_pos + MARGIN), "Last departure", 
                              font=font_small, fill=BLACK)
                    break  # Don't show more times after "Last departure"
                elif message == "theor.":
                    draw.text((msg_x, y_pos + MARGIN), "(theor.)", 
                              font=font_small, fill=BLACK)
                elif message:
                    draw.text((msg_x, y_pos + MARGIN), msg_text, 
                              font=font_small, fill=BLACK)
            
            # Move x position for next time
            x_pos += time_width + message_width + MARGIN + EXTRA_SPACING  # Add spacing between times
            max_width -= (time_width + message_width + MARGIN + EXTRA_SPACING)  # Deduct used width
            times_shown += 1

    # Draw current time at the bottom
    current_time = datetime.now().strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_small)
    time_width = time_bbox[2] - time_bbox[0]
    time_height = time_bbox[3] - time_bbox[1]
    
    # Adjust time position based on number of bus lines
    if len(bus_data) == 1:
        time_y = Himage.height - time_height - MARGIN
    else:
        time_y = Himage.height - time_height - MARGIN
    
    draw.text((Himage.width - time_width - MARGIN, time_y), 
              current_time, font=font_small, fill=BLACK)

    # Draw error message if present
    if error_message:
        error_bbox = draw.textbbox((0, 0), error_message, font=font_small)
        error_width = error_bbox[2] - error_bbox[0]
        error_x = (Himage.width - error_width) // 2
        error_y = time_y + time_height + MARGIN if len(bus_data) == 1 else second_box_y + BOX_HEIGHT + MARGIN
        draw.text((error_x, error_y), error_message, font=font_small, fill=RED)

    # Draw a border around the display
    border_color = getattr(epd, 'RED', epd.BLACK)  # Fall back to BLACK if RED not available
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=border_color)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)
    with display_lock:
        # Convert image to buffer
        buffer = epd.getbuffer(Himage)
        
        # Add debug log before display command
        logger.debug("About to call epd.display() with new buffer")
        epd.display(buffer)

def draw_weather_display(epd, weather_data, last_weather_data=None):
    """Draw a weather-focused display when no bus times are available"""
        # Handle different color definitions
    BLACK = epd.BLACK
    WHITE = epd.WHITE
    RED = getattr(epd, 'RED', BLACK)  # Fall back to BLACK if RED not available
    YELLOW = getattr(epd, 'YELLOW', BLACK)  # Fall back to BLACK if YELLOW not available

    # Create a new image with white background
    if epd.is_bw_display:
        Himage = Image.new('1', (epd.height, epd.width), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (epd.height, epd.width), WHITE)

 # 250x120 width x height
    draw = ImageDraw.Draw(Himage)
    font_paths = get_font_paths()
    try:
        font_xl = ImageFont.truetype(font_paths['dejavu_bold'], 42)
        font_large = ImageFont.truetype(font_paths['dejavu_bold'], 28)
        font_medium = ImageFont.truetype(font_paths['dejavu'], 18)
        font_small = ImageFont.truetype(font_paths['dejavu'], 14)
        font_tiny = ImageFont.truetype(font_paths['dejavu'], 10)
    except:
        font_xl = ImageFont.load_default()
        font_large = font_medium = font_small = font_tiny = font_xl 

    MARGIN = 5
    
    # Top row: Large temperature and weather icon
    temp_text = f"{weather_data['current']['temperature']}°C"
    
    # Get and draw weather icon
    icon = get_weather_icon(weather_data['current']['icon'], CURRENT_ICON_SIZE, epd)
    
    # Center temperature and icon
    temp_bbox = draw.textbbox((0, 0), temp_text, font=font_xl)
    temp_width = temp_bbox[2] - temp_bbox[0]
    
    total_width = temp_width + CURRENT_ICON_SIZE[0] + 65
    # start_x = (Himage.width - total_width) // 2
    start_x = MARGIN
    
    # Draw temperature
    draw.text((start_x, MARGIN), temp_text, font=font_xl, fill=epd.BLACK, align="left")
    
    # Draw icon
    if icon:
        icon_x = start_x + temp_width + 20
        icon_y = MARGIN
        Himage.paste(icon, (icon_x, icon_y))
    else:
        # Fallback to text icon if image loading fails
        weather_icon = WEATHER_ICONS.get(weather_data['current']['description'], '?')
        draw.text((start_x + temp_width + 20, MARGIN), weather_icon, 
                  font=font_xl, fill=epd.BLACK)

    # Middle row: Next sun event (moved left and smaller)
    y_pos = 55
    
    # Show either sunrise or sunset based on time of day
    if weather_data['is_daytime']:
        sun_text = f"{weather_data['sunset']}"
        sun_icon = "☀"
    else:
        sun_text = f"{weather_data['sunrise']}"
        sun_icon = "☀"
    
    # Draw sun info on left side with smaller font
    sun_full = f"{sun_icon} {sun_text}"
    draw.text((MARGIN , y_pos), sun_full, font=font_medium, fill=epd.BLACK)

    # Bottom row: Three day forecast (today + next 2 days)
    y_pos = 85
    logger.debug(f"Forecasts: {weather_data['forecasts']}")
    forecasts = weather_data['forecasts'][:3]
    logger.debug(f"Forecasts: {forecasts}")
    
    # Calculate available width
    available_width = Himage.width - (2 * MARGIN)
    # Width for each forecast block (icon + temp)
    forecast_block_width = available_width // 3
    
    for idx, forecast in enumerate(forecasts):
        # Calculate starting x position for this forecast block
        current_x = MARGIN + (idx * forecast_block_width)
        
        # Get and draw icon
        icon = get_weather_icon(forecast['icon'], FORECAST_ICON_SIZE, epd)
        if icon:
            # Center icon and text within their block
            forecast_text = f"{forecast['min']}-{forecast['max']}°"
            text_bbox = draw.textbbox((0, 0), forecast_text, font=font_medium)
            text_width = text_bbox[2] - text_bbox[0]
            total_element_width = FORECAST_ICON_SIZE[0] + 5 + text_width
            
            # Center the whole block
            block_start_x = current_x + (forecast_block_width - total_element_width) // 2
            
            # Draw icon and text
            icon_y = y_pos + (font_medium.size - FORECAST_ICON_SIZE[1]) // 2
            Himage.paste(icon, (block_start_x, icon_y))
            
            # Draw temperature
            text_x = block_start_x + FORECAST_ICON_SIZE[0] + 3
            draw.text((text_x, y_pos), forecast_text, font=font_medium, fill=epd.BLACK)

    # Generate and draw QR code (larger size)
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    qr_code_address = os.getenv("weather_mode_qr_code_address", "http://raspberrypi.local:5002/debug")
    qr.add_data(qr_code_address)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')
    
    # Scale QR code to larger size
    qr_size = 60
    qr_img = qr_img.resize((qr_size, qr_size))
    qr_x = Himage.width - qr_size - MARGIN
    qr_y = MARGIN
    Himage.paste(qr_img, (qr_x, qr_y))

    # Draw time under QR code
    current_time = datetime.now().strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_tiny)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = Himage.width - time_width - MARGIN
    time_y = Himage.height - time_bbox[3]- (MARGIN // 2)
    draw.text((time_x, time_y), 
              current_time, font=font_tiny, fill=epd.BLACK, align="right")

    # Draw a border around the display
    # border_color = getattr(epd, 'RED', epd.BLACK)  # Fall back to BLACK if RED not available
    # draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=border_color)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)
    
    with display_lock:  
        # Display the image
        buffer = epd.getbuffer(Himage)
        epd.display(buffer)

def check_flights_and_update_display(epd, get_flights, flight_check_interval=10):
    """Check for flights within 3 km and update the display if any are found."""
    while True:
        try:
            flights_within_3km = get_flights()
            if flights_within_3km:
                logger.info(f"Flights within the set radius: {len(flights_within_3km)}")
                
                closest_flight = flights_within_3km[0]
                # If the closest flight is on the ground, don't show it and get the next one
                if closest_flight.get('altitude') == "ground":
                    logger.debug("Closest flight is on the ground. Looking for next airborne flight.")
                    found_airborne = False
                    for flight in flights_within_3km[1:]:
                        if flight.get('altitude') != "ground":
                            closest_flight = flight
                            found_airborne = True
                            break
                    if not found_airborne:
                        logger.debug("No airborne flights found in the list.")
                        closest_flight = None
                
                # Enhance the flight data with additional details
                if closest_flight:
                    logger.debug(f"Closest flight: {closest_flight}")
                    enhanced_flight = enhance_flight_data(closest_flight)
                    logger.debug(f"Enhanced flight: {enhanced_flight}")
                    # Update display with the enhanced flight data
                    update_display_with_flights(epd, [enhanced_flight])
            else:
                logger.debug("No flights found within the radius")
            
            # Always sleep before next check, regardless of whether flights were found
            time.sleep(flight_check_interval)

        except Exception as e:
            logger.error(f"Error in flight check loop: {e}", exc_info=True)
            # Sleep on error to prevent rapid error loops
            time.sleep(flight_check_interval)

def update_display_with_flights(epd, flights):
    """Update the display with flight information."""
    # Create a new image with mode 'RGB'
    width = epd.height  # Account for rotation
    height = epd.width
    if epd.is_bw_display:
        Himage = Image.new('1', (width, height), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(Himage)

    # Get font paths based on the operating system
    
    font_paths = get_font_paths()
    # Try to load fonts
    try:
        font_tiny = ImageFont.truetype(font_paths['dejavu'], 10)
        font_small = ImageFont.truetype(font_paths['dejavu'], 12)
        font_medium = ImageFont.truetype(font_paths['dejavu_bold'], 15)
        font_large = ImageFont.truetype(font_paths['dejavu_bold'], 24)
        font_xl = ImageFont.truetype(font_paths['dejavu_bold'], 36) 
        emoji_font = ImageFont.truetype(font_paths['emoji'], 16)
        emoji_font_large = ImageFont.truetype(font_paths['emoji'], 20)
        logger.debug(f"Loaded fonts successfully from paths: {font_paths}")
    except IOError as e:
        logger.error(f"Failed to load fonts: {str(e)}")
        font_tiny = font_small = font_medium = font_large = font_xl = emoji_font = emoji_font_large = ImageFont.load_default()

    MARGIN = 8  # Slightly smaller margin
    flight_details = flights[0]

    # Top section: Flight number and operator
    if not flight_details:
        logger.error(f"Flight details not found: {flight_details}")
        return
    operator = flight_details.get('operator_name', '')
    flight_number = flight_details.get('flight_number', '')
    flight_number_font_size = font_small if aeroapi_enabled else font_medium
    if not flight_number:
        flight_number = flight_details.get('registration', '')
    
    # Draw operator name
    if operator:
        operator_name = operator.get('name', '') if isinstance(operator, dict) else operator
        # Trim operator name if it's too long
        operator_font_size = font_small
        if len(operator_name) > 15:
            operator_font_size = font_tiny
            operator_name = operator_name[:18] + "..."
        draw.text((MARGIN, MARGIN), operator_name, fill='black', font=operator_font_size)
    else:
        callsign = flight_details.get('callsign', " ")
        operator_font_size = font_medium
        draw.text((MARGIN, MARGIN), callsign, fill='black', font=operator_font_size)
    # Draw flight number with plane emoji
    # Split emoji and text to use different fonts
    draw.text((width - 85 - MARGIN, MARGIN), "✈️", fill='black', font=emoji_font)
    draw.text((width - 60 - MARGIN, MARGIN), flight_number, fill='black', font=flight_number_font_size)

    # Draw horizontal line under header
    if aeroapi_enabled:
        draw.line([(MARGIN, 22), (width - MARGIN, 22)], fill='black', width=1)

    # Main section: Origin -> Distance -> Destination
    y_pos = 16  # Moved up even further
    distance_font_size = font_small if aeroapi_enabled else font_medium
    # Draw distance at the top
    distance = f"{flight_details['last_distance']:.1f}km"
    distance_bbox = draw.textbbox((0, 0), distance, font=distance_font_size)
    distance_width = distance_bbox[2] - distance_bbox[0]
    distance_x = (width - distance_width) // 2
    if aeroapi_enabled:
        draw.text((distance_x, MARGIN), distance, fill='black', font=distance_font_size)
    else:
        draw.text((distance_x, height//2 - distance_font_size.size//2-5), distance, fill='black', font=distance_font_size)
    
    # Origin and Destination (moved up)
    y_pos = y_pos + 10  # Reduced spacing further
    
    # Origin
    origin_code = flight_details.get('origin_code', '')
    draw.text((MARGIN, y_pos), origin_code, fill='black', font=font_xl)
    # Draw origin city name below the code, but closer
    draw.text((MARGIN, y_pos + font_xl.size+3 ), flight_details.get('origin_city', ''), fill='black', font=font_tiny)
    
    # Draw arrow
    if flight_details.get('origin_code', '') or flight_details.get('destination_code', ''): 
        arrow = "→"
        arrow_bbox = draw.textbbox((0, 0), arrow, font=font_large)
        arrow_width = arrow_bbox[2] - arrow_bbox[0]
        arrow_x = (width - arrow_width) // 2
        draw.text((arrow_x, y_pos + 8), arrow, fill='black', font=font_large)
    
    # Destination
    dest_code = flight_details.get('destination_code', '')
    dest_city = flight_details.get('destination_city', '')
    dest_bbox = draw.textbbox((0, 0), dest_code, font=font_xl)
    dest_width = dest_bbox[2] - dest_bbox[0]
    dest_x = width - dest_width - MARGIN
    
    # Draw destination code
    draw.text((dest_x, y_pos), dest_code, fill='black', font=font_xl)
    # Draw destination city name below the code, but closer
    dest_city_bbox = draw.textbbox((0, 0), dest_city, font=font_tiny)
    dest_city_width = dest_city_bbox[2] - dest_bbox[0]
    dest_city_x = width - dest_city_width - MARGIN
    draw.text((dest_city_x, y_pos + font_xl.size+3), dest_city, fill='black', font=font_tiny)

    # Bottom section: Aircraft details
    bottom_y = height - 25  # Moved up slightly
    
    # Draw horizontal line above bottom section
    draw.line([(MARGIN, bottom_y - 15), (width - MARGIN, bottom_y - 15)], fill='black', width=1)
    
    # Aircraft type with emoji
    if flight_details.get('type', ''):
        type_length = len(flight_details.get('manufacturer', '')) + len(flight_details.get('type', '')) + 1
    else:
        type_length = len(flight_details.get('description', ''))
    if flight_details.get('type', ''):
        type_text = f"{flight_details.get('manufacturer', '')} {flight_details.get('type', '')}"
    else:
        type_text = f"{flight_details.get('description', '')}"
    
    if type_length > 15:
        type_text = type_text[:15] + "..."
    draw.text((MARGIN, bottom_y - 3), "🛩️", fill='black', font=emoji_font)
    draw.text((MARGIN + 20, bottom_y - 3), type_text, fill='black', font=font_small)
    
    # Altitude with emoji
    if flight_details.get('altitude') == "ground":
        draw.text((width - 50 - MARGIN, bottom_y - 3), "On the ground", fill='black', font=font_small)
    else:
        if not flight_altitude_convert_feet:
            alt_text = f"{flight_details.get('altitude', '')} ft"
        else:
            altitude_in_meters = float(flight_details.get('altitude', '')) * 0.3048
            alt_text = f"{altitude_in_meters:.0f} m"
        draw.text((width - 85 - MARGIN, bottom_y - 3), "⛰️", fill='black', font=emoji_font)
        draw.text((width - 60 - MARGIN, bottom_y - 3), alt_text, fill='black', font=font_small)

    # Rotate image for display
    Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)
    
    # Display the image
    with display_lock:
        buffer = epd.getbuffer(Himage)
        epd.display(buffer)

def main():
    epd = None
    try:
        logger.info("E-ink Display Starting")
        
        # Start debug server if enabled
        start_debug_server()
        
        # Initialize display using adapter
        logger.debug("About to initialize display")
        epd = DisplayAdapter.get_display()
        
        # Add debug logs before EPD commands
        logger.debug("About to call epd.init()")
        try:
            with display_lock:
                epd.init()
        except Exception as e:
            logger.error(f"Error initializing display: {str(e)}\n{traceback.format_exc()}")
            raise
        
        logger.debug("About to call epd.Clear()")
        try:
            with display_lock:
                epd.Clear()
        except Exception as e:
            logger.error(f"Error clearing display: {str(e)}\n{traceback.format_exc()}")
            raise
        logger.info("Display initialized")
        
        logger.debug("About to call epd.init_Fast()")
        with display_lock:
            epd.init_Fast()
        logger.info("Fast mode initialized")
        
        # Check Wi-Fi connectivity
        if not is_connected():
            logger.info("Not connected to Wi-Fi. Starting Wi-Fi manager...")
            subprocess.Popen(['python3', 'wifi_manager.py'])
            with display_lock:
                show_no_wifi_display(epd)
            
            # Wait and check for WiFi connection
            while not is_connected():
                logger.info("Waiting for WiFi connection...")
                time.sleep(30)  # Check every 30 seconds
            
            logger.info("WiFi connected. Continuing with main loop...")
            # Reinitialize display after WiFi setup
            with display_lock:
                epd.init()
                epd.Clear()
                epd.init_Fast()

        # Initialize services
        weather = WeatherService() if weather_enabled else None
        bus = BusService()
        
        # Initialize flight monitoring
        if flights_enabled:
            search_radius = FLIGHT_MAX_RADIUS * 2
            get_flights = gather_flights_within_radius(
                COORDINATES_LAT, 
                COORDINATES_LNG, 
                search_radius, 
                FLIGHT_MAX_RADIUS, 
                flight_check_interval=flight_check_interval,
                aeroapi_enabled=aeroapi_enabled
            )
            
            # Start flight checking in a separate thread
            flight_thread = threading.Thread(
                target=check_flights_and_update_display,
                args=(epd, get_flights, flight_check_interval),
                daemon=True
            )
            flight_thread.start()
        
        # Counter for full refresh every hour
        update_count = 0
        FULL_REFRESH_INTERVAL = DISPLAY_REFRESH_FULL_INTERVAL // DISPLAY_REFRESH_INTERVAL  # Number of updates before doing a full refresh
        
        # Add variables for weather display
        last_weather_data = None
        last_weather_update = datetime.now()
        WEATHER_UPDATE_INTERVAL = DISPLAY_REFRESH_WEATHER_INTERVAL  # 10 minutes in seconds
        in_weather_mode = False  # Track which mode we're in
        
        # Main loop
        while True:
            try:
                # Get data
                if weather_enabled:
                    weather_data = weather.get_detailed_weather()
                else:
                    weather_data = None
                
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
                    with display_lock:
                        epd.init()
                    logger.debug("About to call epd.Clear()")
                    with display_lock:
                        epd.Clear()
                    logger.debug("About to call epd.init_Fast()")
                    with display_lock:
                        epd.init_Fast()
                    update_count = 0
                
                # Determine display mode
                if valid_bus_data:
                    # Bus display mode
                    in_weather_mode = False
                    last_weather_data = None  # Reset weather tracking
                    last_weather_update = current_time
                    if weather_enabled:
                        update_display(epd, weather_data['current'], valid_bus_data, error_message, stop_name)
                    else:
                        weather_data = None
                        update_display(epd, weather_data, valid_bus_data, error_message, stop_name)
                    wait_time = DISPLAY_REFRESH_INTERVAL if not error_message else DISPLAY_REFRESH_MINIMAL_TIME
                    update_count += 1
                elif weather_enabled:
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
                        with display_lock:
                            draw_weather_display(epd, weather_data)
                        last_weather_data = weather_data
                        last_weather_update = current_time
                    
                    # In weather mode, we wait longer between checks
                    wait_time = WEATHER_UPDATE_INTERVAL
                
                # Log next update info
                if in_weather_mode:
                    next_update = f"weather update in {wait_time} seconds"
                else:
                    wait_time = DISPLAY_REFRESH_WEATHER_INTERVAL 
                    updates_until_refresh = FULL_REFRESH_INTERVAL - update_count - 1
                    next_update = f"public transport update in {wait_time} seconds ({updates_until_refresh} until full refresh)"
                
                logger.info(f"Waiting {wait_time} seconds until next update ({next_update})")
                time.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(10)
                continue
            
    except KeyboardInterrupt:
        logger.info("Ctrl+C pressed - Cleaning up...")
        
    except Exception as e:
        logger.error(f"Main error: {str(e)}\n{traceback.format_exc()}")
        
    finally:
        logger.info("Cleaning up...")
        if epd is not None:
            try:
                logger.debug("About to call final epd.init()")
                with display_lock:
                    epd.init()
                logger.debug("About to call final epd.Clear()")
                with display_lock:
                    epd.Clear()
                logger.debug("About to call epd.sleep()")
                with display_lock:
                    epd.sleep()
                logger.debug("About to call module_exit")
                with display_lock:
                    epd.epdconfig.module_exit(cleanup=True)
                logger.info("Display cleanup completed")
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}\n{traceback.format_exc()}")
        sys.exit(0)

if __name__ == "__main__":
    main()
