from typing import Tuple
import logging
import log_config
logger = logging.getLogger(__name__)

def calculate_brightness(rgb_or_value):
    """
    Calculate perceived brightness of a color (0-1)
    Using the formula from W3C accessibility guidelines
    """
    if isinstance(rgb_or_value, tuple):
        r, g, b = rgb_or_value
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255
    else:
        # For monochrome displays, value is already 0x00 (0) or 0xFF (255)
        return rgb_or_value / 255 if rgb_or_value > 0 else 0

def draw_multicolor_dither(draw, epd, x, y, width, height, colors_with_ratios):
    """
    Draw a dithered pattern using multiple colors with specified ratios.
    colors_with_ratios is a list of tuples (color_name, ratio)
    """
    # Get available colors from EPD
    available_colors = _get_available_colors(epd)
    
    # Validate colors
    for color_name, _ in colors_with_ratios:
        if color_name not in available_colors:
            logger.warning(f"Color {color_name} not supported by display, falling back to black")
            color_name = 'black'
    
    # Create checkerboard pattern with offset rows
    for i in range(width):
        for j in range(height):
            # Offset every other row by one pixel
            offset = (j % 2) * 1
            pos = ((i + offset + j) % 2) / 2 + (i + j) / (width + height)
            
            # Select color based on position and ratios
            cumulative_ratio = 0
            selected_color = available_colors['white'][0]  # Default to white
            
            for color_name, ratio in colors_with_ratios:
                cumulative_ratio += ratio
                if pos <= cumulative_ratio:
                    selected_color = available_colors[color_name][0]
                    break
            
            draw.point((x + i, y + j), fill=selected_color)
    
    # Draw border in primary color (first color in the list)
    primary_color = colors_with_ratios[0][0]
    draw.rectangle([x, y, x + width - 1, y + height - 1], 
                  outline=available_colors[primary_color][0])

def draw_dithered_box(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """
    Draw a box with dithered background and centered text.
    Uses offset checkerboard pattern which provides the best visual results on e-paper display.
    This is the primary dithering function used in the application.
    """
    logging.debug(f"Drawing dithered box with colors: {primary_color} ({ratio:.2f}) and {secondary_color} ({1-ratio:.2f})")
    
    # Get available colors from EPD
    available_colors = {
        'black': (epd.BLACK, (0, 0, 0) if isinstance(epd.BLACK, tuple) else epd.BLACK),
        'white': (epd.WHITE, (255, 255, 255) if isinstance(epd.WHITE, tuple) else epd.WHITE)
    }
    
    # Add red and yellow only if they're different from BLACK
    if hasattr(epd, 'RED') and epd.RED != epd.BLACK:
        available_colors['red'] = (epd.RED, (255, 0, 0) if isinstance(epd.RED, tuple) else epd.RED)
    if hasattr(epd, 'YELLOW') and epd.YELLOW != epd.BLACK:
        available_colors['yellow'] = (epd.YELLOW, (255, 255, 0) if isinstance(epd.YELLOW, tuple) else epd.YELLOW)
    
    # Validate requested colors
    if primary_color not in available_colors:
        logger.warning(f"Primary color {primary_color} not supported by display, falling back to black")
        primary_color = 'black'
    if secondary_color not in available_colors:
        logger.warning(f"Secondary color {secondary_color} not supported by display, falling back to white")
        secondary_color = 'white'
    
    primary_epd, primary_rgb = available_colors[primary_color]
    secondary_epd, secondary_rgb = available_colors[secondary_color]
    
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
    
    # Choose text color based on background darkness
    # If primary color is dark (black) and dominant, use white text
    if primary_color == 'black' and ratio > 0.5:
        text_color = available_colors['white'][0]
    else:
        text_color = available_colors['black'][0]
    
    draw.text((text_x, text_y), text, font=font, fill=text_color)

def _get_available_colors(epd):
    """Helper function to get available colors for the display"""
    colors = {
        'black': (getattr(epd, 'BLACK', 0x000000), (0, 0, 0)),
        'white': (getattr(epd, 'WHITE', 0xffffff), (255, 255, 255))
    }
    
    if hasattr(epd, 'RED'):
        colors['red'] = (epd.RED, (255, 0, 0))
    if hasattr(epd, 'YELLOW'):
        colors['yellow'] = (epd.YELLOW, (255, 255, 0))
    
    return colors

def draw_horizontal_lines_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Horizontal line pattern - experimental"""
    colors = _get_available_colors(epd)
    if primary_color not in colors or secondary_color not in colors:
        logger.warning("Unsupported colors requested, falling back to black/white")
        primary_color = 'black'
        secondary_color = 'white'
    
    primary, _ = colors[primary_color]
    secondary, _ = colors[secondary_color]
    
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