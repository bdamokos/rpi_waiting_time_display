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
from dataclasses import dataclass
from typing import Tuple, Optional, List

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

@dataclass
class GridBlock:
    """Represents a rectangular area of blocks in the grid"""
    x_start: int  # Starting x coordinate in blocks
    y_start: int  # Starting y coordinate in blocks
    x_end: int    # Ending x coordinate in blocks (exclusive)
    y_end: int    # Ending y coordinate in blocks (exclusive)
    content_type: str

class DisplayGrid:
    def __init__(self, width: int, height: int, block_size: int = 10):
        self.width = width    # 250 pixels
        self.height = height  # 120 pixels
        self.block_size = block_size
        
        # Define the grid layout with correct x,y coordinates
        self.layout = [
            # Main temperature and condition (x:0-80, y:0-80)
            GridBlock(0, 0, 80, 80, 'main_temp_condition'),
            
            # Feels like (x:80-140, y:0-80)
            GridBlock(80, 0, 140, 80, 'feels_like'),
            
            # Today's temps (x:140-200, y:0-80)
            GridBlock(140, 0, 200, 80, 'today_temps'),
            
            # Reserved space (x:200-250, y:0-40)
            GridBlock(200, 0, 250, 40, 'reserved'),
            
            # Sunrise/Sunset (x:0-40, y:80-120)
            GridBlock(0, 80, 40, 120, 'sun_time'),
            
            # AQI (x:40-100, y:80-120)
            GridBlock(40, 80, 100, 120, 'aqi'),
            
            # Next 3 days forecast (x:100-200, y:80-120)
            GridBlock(100, 80, 200, 120, 'forecast'),
            
            # Current date and time (x:200-250, y:80-120)
            GridBlock(200, 80, 250, 120, 'datetime'),
            
            # QR code (x:200-250, y:20-100)
            GridBlock(200, 20, 250, 100, 'qr')
        ]
    
    def get_pixel_bounds(self, block: GridBlock) -> Tuple[int, int, int, int]:
        """Convert pixel coordinates to block coordinates"""
        x = block.x_start // self.block_size
        y = block.y_start // self.block_size
        width = (block.x_end - block.x_start) // self.block_size
        height = (block.y_end - block.y_start) // self.block_size
        return (x, y, width, height)
    
    def render_debug_grid(self) -> List[Image.Image]:
        """Create debug visualizations of the grid with rotated display boundaries"""
        # Calculate the maximum coordinates needed from layout
        max_x = max(block.x_end for block in self.layout) * self.block_size
        max_y = max(block.y_end for block in self.layout) * self.block_size
        
        # Create image with enough space to show all blocks
        debug_width = max(self.width, max_x + self.block_size)
        debug_height = max(self.height, max_y + self.block_size)
        
        # Create base image
        img = Image.new('RGB', (debug_width, debug_height), 'white')
        draw = ImageDraw.Draw(img)
        
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 8)
        except:
            font = ImageFont.load_default()
        
        # Draw block grid
        for x in range(0, debug_width + 1, self.block_size):
            draw.line([(x, 0), (x, debug_height)], fill='lightgray')
            draw.text((x + 2, 2), str(x//10), font=font, fill='gray')
        
        for y in range(0, debug_height + 1, self.block_size):
            draw.line([(0, y), (debug_width, y)], fill='lightgray')
            draw.text((2, y + 2), str(y//10), font=font, fill='gray')
        
        # Draw content areas with coordinates
        for block in self.layout:
            x, y, w, h = self.get_pixel_bounds(block)
            
            # Flip the y-axis and adjust for row offset
            y = debug_height - y - h - self.block_size

            # Use different colors for blocks inside/outside physical display
            if (x + w <= self.width and y + h <= self.height):
                outline_color = 'blue'
            else:
                outline_color = 'orange'  # Highlight blocks that exceed display bounds
            
            draw.rectangle([(x, y), (x + w - 1, y + h - 1)], outline=outline_color)
            
            label = f"{block.content_type}\n({block.x_start},{block.y_start})-({block.x_end},{block.y_end})"
            draw.text((x + 5, y + 5), label, font=font, fill='black')
        
        # Generate images with rotated display boundaries
        rotations = []
        for angle in [0, 90, 180, 270]:
            rotated_img = img.copy()
            rotated_draw = ImageDraw.Draw(rotated_img)
            
            # Draw the display boundary in each rotation
            if angle == 0:
                rotated_draw.rectangle([(0, 0), (self.width-1, self.height-1)], outline='red')
            elif angle == 90:
                rotated_draw.rectangle([(0, 0), (self.height-1, self.width-1)], outline='red')
            elif angle == 180:
                rotated_draw.rectangle([(debug_width - self.width, debug_height - self.height), (debug_width-1, debug_height-1)], outline='red')
            elif angle == 270:
                rotated_draw.rectangle([(debug_height - self.height, debug_width - self.width), (debug_height-1, debug_width-1)], outline='red')
            
            rotations.append(rotated_img)
        
        return rotations

def calculate_font_size(text: str, target_width: int, target_height: int, max_ratio: float = 0.8) -> int:
    """Calculate the largest font size that will fit in the target dimensions"""
    font_size = 1
    font = None
    
    # Binary search for the right font size
    min_size = 1
    max_size = min(target_width, target_height)
    
    while min_size <= max_size:
        current_size = (min_size + max_size) // 2
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', current_size)
        except:
            return current_size  # Fallback if font loading fails
            
        bbox = font.getbbox(text)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        if (text_width <= target_width * max_ratio and 
            text_height <= target_height * max_ratio):
            font_size = current_size
            min_size = current_size + 1
        else:
            max_size = current_size - 1
    
    return font_size

def render_cell(cell_type: str, data: dict, width: int, height: int) -> Image.Image:
    """Render a cell directly at target size"""
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)
    
    if cell_type == 'qr':
        # Handle QR code separately
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data('http://raspberrypi.local:5001')
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.convert('RGB')
        qr_size = min(width, height) - 4
        qr_img = qr_img.resize((qr_size, qr_size))
        x = (width - qr_size) // 2
        y = (height - qr_size) // 2
        img.paste(qr_img, (x, y))
        return img

    # Prepare text content based on cell type
    if cell_type == 'main_temp':
        text = f"{data['current']['temperature']}°"
        max_ratio = 0.9  # Allow temperature to be larger
    elif cell_type == 'weather_icon':
        text = WEATHER_ICONS.get(data['current']['description'], '?')
        max_ratio = 0.8
    elif cell_type == 'wind_humidity':  # Changed from 'wind'
        text = f"↓{data['wind_speed']}\n{data['humidity']}%"  # Combined wind and humidity
        max_ratio = 0.7
    elif cell_type == 'sun_time':
        text = f"☀↓{data['sunset']}" if data['is_daytime'] else f"☀↑{data['sunrise']}"
        max_ratio = 0.7
    elif cell_type == 'today_temp':
        text = f"▼{data['current']['temperature']}° ▲{data['current']['temperature']}°"
        max_ratio = 0.7
    elif cell_type == 'tomorrow_temp':
        text = f"▼{data['tomorrow']['min']}° ▲{data['tomorrow']['max']}°"
        max_ratio = 0.7
    elif cell_type == 'pressure':
        text = f"{data['current'].get('pressure', '--')}hPa"
        max_ratio = 0.6
    elif cell_type == 'feels_like':
        text = f"Feel:{data['current'].get('feels_like', '--')}°"
        max_ratio = 0.6
    elif cell_type == 'time':
        text = datetime.now().strftime("%H:%M")
        max_ratio = 0.7
    elif cell_type == 'aqi':
        if data['tomorrow'].get('air_quality'):
            text = f"AQI:{data['tomorrow']['air_quality']['aqi']}"
        else:
            text = "AQI:--"
        max_ratio = 0.6
    else:
        text = "?"  # Fallback for unknown cell types
        max_ratio = 0.7
    
    # For multiline text
    if '\n' in text:
        lines = text.split('\n')
        line_heights = []
        line_widths = []
        
        # Calculate optimal font size for all lines
        for line in lines:
            font_size = calculate_font_size(line, width, height // len(lines), max_ratio)
            line_heights.append(font_size)
            
        # Use smallest font size that fits all lines
        font_size = min(line_heights)
    else:
        font_size = calculate_font_size(text, width, height, max_ratio)
    
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', font_size)
    except:
        font = ImageFont.load_default()
    
    # Draw text centered in cell
    if '\n' in text:
        lines = text.split('\n')
        total_height = sum(font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines)
        y = (height - total_height) // 2
        
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            draw.text((x, y), line, font=font, fill='black')
            y += font.getbbox(line)[3] - font.getbbox(line)[1]
    else:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        draw.text((x, y), text, font=font, fill='black')
    
    return img

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

def draw_weather_display(epd, weather_data):
    """Draw weather display using grid system"""
    # Create base image in logical orientation (250x120)
    # Note: epd.height is 120, epd.width is 250 in physical orientation
    Himage = Image.new('RGB', (epd.width, epd.height), epd.WHITE)  # 250x120
    grid = DisplayGrid(epd.width, epd.height)  # 250x120
    
    # Initialize fonts
    try:
        font_xl = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 48)
        font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 36)
        font_medium = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 24)
        font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 16)
    except:
        font_xl = font_large = font_medium = font_small = ImageFont.load_default()
        logger.warning("Failed to load fonts, using default font")

    # Debug: Save grid visualization
    debug_grids = grid.render_debug_grid()
    debug_grids[0].save('debug_grid_original.png')
    
    for block in grid.layout:
        # Get coordinates in 250x120 space
        x, y, w, h = grid.get_pixel_bounds(block)
        
        # Render cell content (no rotation needed)
        cell_img = None
        
        if block.content_type == 'main_temp_condition':
            # Current temperature and weather icon
            temp_img = Image.new('RGB', (w//2, h), 'white')
            temp_draw = ImageDraw.Draw(temp_img)
            temp_text = f"{weather_data['current']['temperature']}°"
            draw_centered_text(temp_draw, temp_text, w//2, h, font_xl)
            
            icon_img = Image.new('RGB', (w//2, h), 'white')
            icon_draw = ImageDraw.Draw(icon_img)
            weather_icon = WEATHER_ICONS.get(weather_data['current']['description'], '?')
            draw_centered_text(icon_draw, weather_icon, w//2, h, font_large)
            
            # Combine temperature and icon
            cell_img = Image.new('RGB', (w, h), 'white')
            cell_img.paste(temp_img, (0, 0))
            cell_img.paste(icon_img, (w//2, 0))
            
        elif block.content_type == 'feels_like':
            cell_img = Image.new('RGB', (w, h), 'white')
            draw = ImageDraw.Draw(cell_img)
            text = f"Feel:{weather_data['current'].get('feels_like', '--')}°"
            draw_centered_text(draw, text, w, h, font_medium)
            
        elif block.content_type == 'today_temps':
            cell_img = Image.new('RGB', (w, h), 'white')
            draw = ImageDraw.Draw(cell_img)
            text = f"▼{weather_data['current']['temperature']}° ▲{weather_data['current']['temperature']}°"
            draw_centered_text(draw, text, w, h, font_medium)
            
        elif block.content_type == 'sun_time':
            cell_img = Image.new('RGB', (w, h), 'white')
            draw = ImageDraw.Draw(cell_img)
            if weather_data['is_daytime']:
                text = f"☀↓{weather_data['sunset']}"
            else:
                text = f"☀↑{weather_data['sunrise']}"
            draw_centered_text(draw, text, w, h, font_medium)
            
        elif block.content_type == 'aqi':
            cell_img = Image.new('RGB', (w, h), 'white')
            draw = ImageDraw.Draw(cell_img)
            if weather_data['tomorrow'].get('air_quality'):
                text = f"AQI:{weather_data['tomorrow']['air_quality']['aqi']}"
            else:
                text = "AQI:--"
            draw_centered_text(draw, text, w, h, font_medium)
            
        elif block.content_type == 'forecast':
            cell_img = Image.new('RGB', (w, h), 'white')
            draw = ImageDraw.Draw(cell_img)
            text = f"▼{weather_data['tomorrow']['min']}° ▲{weather_data['tomorrow']['max']}°"
            draw_centered_text(draw, text, w, h, font_medium)
            
        elif block.content_type == 'datetime':
            cell_img = Image.new('RGB', (w, h), 'white')
            draw = ImageDraw.Draw(cell_img)
            text = datetime.now().strftime("%H:%M")
            draw_centered_text(draw, text, w, h, font_medium)
            
        elif block.content_type == 'qr':
            qr = qrcode.QRCode(version=1, box_size=2, border=1)
            qr.add_data('http://raspberrypi.local:5001')
            qr.make(fit=True)
            cell_img = qr.make_image(fill_color="black", back_color="white")
            cell_img = cell_img.convert('RGB')
            cell_img = cell_img.resize((min(w, h), min(w, h)))
            
            # Center QR code in cell if needed
            if cell_img.size != (w, h):
                temp_img = Image.new('RGB', (w, h), 'white')
                x_offset = (w - cell_img.width) // 2
                y_offset = (h - cell_img.height) // 2
                temp_img.paste(cell_img, (x_offset, y_offset))
                cell_img = temp_img
        
        # Paste the cell directly (no rotation needed)
        if cell_img:
            Himage.paste(cell_img, (x, y))
    
    # Draw border around the entire display
    draw = ImageDraw.Draw(Himage)
    draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline='black')
    
    # Save pre-rotation image for debugging
    Himage.save('pre_rotation.png')
    
    # Rotate the final image to match display orientation (90° counterclockwise)
    # This will give us 120x250 which is what the display expects
    Himage = Himage.rotate(90, expand=True)
    
    # Save post-rotation image for debugging
    Himage.save('post_rotation.png')
    
    # Display the rotated image
    buffer = epd.getbuffer(Himage)
    epd.display(buffer)

def draw_centered_text(draw: ImageDraw, text: str, width: int, height: int, font: ImageFont, fill='black'):
    """Helper to draw centered text in a cell"""
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    draw.text((x, y), text, font=font, fill=fill)

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
