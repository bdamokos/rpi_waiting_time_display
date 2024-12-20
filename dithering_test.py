#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import logging
from display_adapter import DisplayAdapter
from PIL import Image, ImageDraw, ImageFont
from bus_service import BusService
from dithering import (
    draw_dithered_box,  # Our current production pattern
    draw_horizontal_lines_dither,
    draw_vertical_lines_dither,
    draw_diagonal_lines_dither,
    draw_dots_dither
)
import log_config

logger = logging.getLogger(__name__)

def main():
    epd = None
    try:
        # Initialize display
        logging.info("Initializing display...")
        epd = DisplayAdapter.get_display()
        epd.init()
        epd.Clear()
        
        # Create image
        Himage = Image.new('RGB', (epd.height, epd.width), epd.WHITE)
        draw = ImageDraw.Draw(Himage)
        logging.info(f"Image dimensions: {Himage.width}x{Himage.height}")
        
        # Load font
        logging.info("Loading fonts...")
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 24)
        small_font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 12)  # Slightly larger for readability
        
        # Get bus colors from service
        logging.info("Getting bus colors...")
        bus_service = BusService()
        
        colors_56 = bus_service.get_line_color("56")
        colors_59 = bus_service.get_line_color("59")
        
        logging.info(f"Line 56 colors: {colors_56}")
        logging.info(f"Line 59 colors: {colors_59}")
        
        # Show fewer patterns with better spacing
        patterns = [
            (draw_dithered_box, "Current"),
            (draw_vertical_lines_dither, "Vertical"),
            (draw_diagonal_lines_dither, "Diagonal")
        ]
        
        # Adjust dimensions for better fit
        box_width = 35
        box_height = 30
        x_start = 15
        x_spacing = 45  # More space between boxes
        y_spacing = 40  # More space between patterns
        
        logging.info("Drawing patterns...")
        for i, (pattern_func, pattern_name) in enumerate(patterns):
            y_pos = 10 + (i * y_spacing)  # Start a bit lower
            logging.info(f"Drawing {pattern_name} pattern...")
            
            # Draw pattern name (vertically aligned with first box)
            draw.text((2, y_pos + 8), pattern_name, font=small_font, fill=epd.BLACK)
            
            # Draw line 56 sample
            pattern_func(draw, epd, x_start + x_spacing, y_pos, box_width, box_height, "56", 
                       colors_56[0], colors_56[1], colors_56[2], font)
            
            # Draw line 59 sample
            pattern_func(draw, epd, x_start + (x_spacing * 3), y_pos, box_width, box_height, "59",
                       colors_59[0], colors_59[1], colors_59[2], font)
        
        # Add title at the bottom
        title = "Alternative Patterns"
        title_bbox = draw.textbbox((0, 0), title, font=small_font)
        title_width = title_bbox[2] - title_bbox[0]
        draw.text((Himage.width - title_width - 5, Himage.height - 15), 
                 title, font=small_font, fill=epd.BLACK)
        
        # Rotate and display
        logging.info("Displaying image...")
        Himage = Himage.rotate(90, expand=True)
        epd.display(epd.getbuffer(Himage))
        
        logging.info("Putting display to sleep...")
        epd.sleep()
            
    except Exception as e:
        logging.error(f"Error: {e}")
        
    finally:
        if epd is not None:
            try:
                logging.info("Cleanup in finally block...")
                epd.epdconfig.module_exit()
            except Exception as e:
                logging.error(f"Error during cleanup: {e}")

if __name__ == '__main__':
    main() 