#!/usr/bin/python
# -*- coding:utf-8 -*-
import sys
import os
import logging
from waveshare_epd import epd2in13g_V2
from PIL import Image, ImageDraw, ImageFont
from bus_service import BusService

logging.basicConfig(level=logging.DEBUG)

def draw_checkerboard_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Classic checkerboard pattern"""
    color_map = {
        'black': epd.BLACK,
        'red': epd.RED,
        'yellow': epd.YELLOW,
        'white': epd.WHITE
    }
    primary = color_map[primary_color]
    secondary = color_map[secondary_color]
    
    for i in range(width):
        for j in range(height):
            use_primary = ((i + j) % 2 == 0) if (i + j) / (width + height) < ratio else \
                         ((i + j) % 2 != 0)
            pixel_color = primary if use_primary else secondary
            draw.point((x + i, y + j), fill=pixel_color)
    
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=primary)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_x = x + (width - (text_bbox[2] - text_bbox[0])) // 2
    text_y = y + (height - (text_bbox[3] - text_bbox[1])) // 2
    draw.text((text_x, text_y), text, font=font, fill=epd.WHITE)

def draw_horizontal_lines_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Horizontal line pattern"""
    color_map = {'black': epd.BLACK, 'red': epd.RED, 'yellow': epd.YELLOW, 'white': epd.WHITE}
    primary, secondary = color_map[primary_color], color_map[secondary_color]
    
    line_height = 2
    for j in range(0, height, line_height):
        color = primary if (j / height) < ratio else secondary
        for i in range(width):
            for k in range(line_height):
                if j + k < height:
                    draw.point((x + i, y + j + k), fill=color)
    
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=primary)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_x = x + (width - (text_bbox[2] - text_bbox[0])) // 2
    text_y = y + (height - (text_bbox[3] - text_bbox[1])) // 2
    draw.text((text_x, text_y), text, font=font, fill=epd.WHITE)

def draw_vertical_lines_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Vertical line pattern"""
    color_map = {'black': epd.BLACK, 'red': epd.RED, 'yellow': epd.YELLOW, 'white': epd.WHITE}
    primary, secondary = color_map[primary_color], color_map[secondary_color]
    
    line_width = 2
    for i in range(0, width, line_width):
        color = primary if (i / width) < ratio else secondary
        for j in range(height):
            for k in range(line_width):
                if i + k < width:
                    draw.point((x + i + k, y + j), fill=color)
    
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=primary)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_x = x + (width - (text_bbox[2] - text_bbox[0])) // 2
    text_y = y + (height - (text_bbox[3] - text_bbox[1])) // 2
    draw.text((text_x, text_y), text, font=font, fill=epd.WHITE)

def draw_diagonal_lines_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Diagonal line pattern"""
    color_map = {'black': epd.BLACK, 'red': epd.RED, 'yellow': epd.YELLOW, 'white': epd.WHITE}
    primary, secondary = color_map[primary_color], color_map[secondary_color]
    
    for i in range(width):
        for j in range(height):
            # Create diagonal pattern
            pattern_value = ((i + j) % 8) / 8  # 8 pixel wide diagonal stripes
            use_primary = pattern_value < ratio
            pixel_color = primary if use_primary else secondary
            draw.point((x + i, y + j), fill=pixel_color)
    
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=primary)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_x = x + (width - (text_bbox[2] - text_bbox[0])) // 2
    text_y = y + (height - (text_bbox[3] - text_bbox[1])) // 2
    draw.text((text_x, text_y), text, font=font, fill=epd.WHITE)

def draw_dots_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Dot pattern"""
    color_map = {'black': epd.BLACK, 'red': epd.RED, 'yellow': epd.YELLOW, 'white': epd.WHITE}
    primary, secondary = color_map[primary_color], color_map[secondary_color]
    
    # Fill background with secondary color
    for i in range(width):
        for j in range(height):
            draw.point((x + i, y + j), fill=secondary)
    
    # Draw dots in primary color
    dot_spacing = 4
    for i in range(0, width, dot_spacing):
        for j in range(0, height, dot_spacing):
            if (i/width + j/height)/2 < ratio:
                draw.point((x + i, y + j), fill=primary)
    
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=primary)
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_x = x + (width - (text_bbox[2] - text_bbox[0])) // 2
    text_y = y + (height - (text_bbox[3] - text_bbox[1])) // 2
    draw.text((text_x, text_y), text, font=font, fill=epd.WHITE)

def main():
    epd = None
    try:
        # Initialize display
        logging.info("Initializing display...")
        epd = epd2in13g_V2.EPD()
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
            (draw_checkerboard_dither, "Current"),
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
                epd2in13g_V2.epdconfig.module_exit()
            except Exception as e:
                logging.error(f"Error during cleanup: {e}")

if __name__ == '__main__':
    main() 