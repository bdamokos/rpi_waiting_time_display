from typing import Tuple
import logging
import log_config
logger = logging.getLogger(__name__)

def calculate_brightness(rgb: Tuple[int, int, int]) -> float:
    """
    Calculate perceived brightness of a color (0-1)
    Using the formula from W3C accessibility guidelines
    """
    r, g, b = rgb
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

def draw_dithered_box(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """
    Draw a box with dithered background and centered text.
    Uses offset checkerboard pattern which provides the best visual results on e-paper display.
    This is the primary dithering function used in the application.
    """
    logging.debug(f"Drawing dithered box with colors: {primary_color} ({ratio:.2f}) and {secondary_color} ({1-ratio:.2f})")
    
    # Map color names to epd colors and RGB values
    color_map = {
        'black': (epd.BLACK, (0, 0, 0)),
        'red': (epd.RED, (255, 0, 0)),
        'yellow': (epd.YELLOW, (255, 255, 0)),
        'white': (epd.WHITE, (255, 255, 255))
    }
    
    primary_epd, primary_rgb = color_map[primary_color]
    secondary_epd, secondary_rgb = color_map[secondary_color]
    
    # Count actual pixels of each color for accurate brightness calculation
    primary_pixel_count = 0
    total_pixels = width * height
    
    # Create checkerboard pattern with offset rows to avoid diagonal lines
    for i in range(width):
        for j in range(height):
            # Offset every other row by one pixel
            offset = (j % 2) * 1
            # Use the offset in the checkerboard calculation
            use_primary = ((i + offset + j) % 2 == 0) if (i + j) / (width + height) < ratio else \
                         ((i + offset + j) % 2 != 0)
            
            if use_primary:
                primary_pixel_count += 1
            pixel_color = primary_epd if use_primary else secondary_epd
            draw.point((x + i, y + j), fill=pixel_color)
    
    # Draw border in primary color
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=primary_epd)
    
    # Calculate text position to center it
    text_bbox = draw.textbbox((0, 0), text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    
    text_x = x + (width - text_width) // 2
    text_y = y + (height - text_height) // 2
    
    # Calculate actual ratio of colors after dithering
    actual_ratio = primary_pixel_count / total_pixels
    
    # Calculate average brightness using actual pixel counts
    avg_brightness = (calculate_brightness(primary_rgb) * actual_ratio + 
                     calculate_brightness(secondary_rgb) * (1 - actual_ratio))
    
    logging.debug(f"Actual dithered ratio: {actual_ratio:.2f}, Brightness: {avg_brightness:.2f}")
    
    # Use black text if background is bright (threshold 0.6)
    text_color = epd.BLACK if avg_brightness > 0.6 else epd.WHITE
    draw.text((text_x, text_y), text, font=font, fill=text_color)

# Alternative dithering patterns - not currently used in production but available for testing
def draw_horizontal_lines_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Horizontal line pattern - experimental"""
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
    """Vertical line pattern - experimental"""
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
    """Diagonal line pattern - experimental"""
    color_map = {'black': epd.BLACK, 'red': epd.RED, 'yellow': epd.YELLOW, 'white': epd.WHITE}
    primary, secondary = color_map[primary_color], color_map[secondary_color]
    
    for i in range(width):
        for j in range(height):
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
    """Dot pattern - experimental"""
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