from typing import Tuple
import logging

from PIL import Image, ImageDraw
from color_utils import find_optimal_colors
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



def draw_dithered_box(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """
    Draw a box with dithered background and centered text.
    Uses offset checkerboard pattern which provides the best visual results on e-paper display.
    This is the primary dithering function used in the application.
    """
    logging.debug(f"Drawing dithered box with colors: {primary_color} ({ratio:.2f}) and {secondary_color} ({1-ratio:.2f})")
    
    # Get available colors from EPD
    available_colors = _get_available_colors(epd)
    
    # Validate requested colors and fall back to B&W if requested colors aren't available
    if primary_color not in available_colors:
        logger.debug(f"Primary color {primary_color} not supported by display, falling back to black")
        primary_color = 'black'
    if secondary_color not in available_colors:
        logger.debug(f"Secondary color {secondary_color} not supported by display, falling back to white")
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
    
    # Choose text color based on background brightness
    # Use white text for dark backgrounds (brightness < 0.5)
    if avg_brightness < 0.5:
        text_color = epd.WHITE if epd.is_bw_display else available_colors['white'][0]
    else:
        text_color = epd.BLACK if epd.is_bw_display else available_colors['black'][0]
    
    draw.text((text_x, text_y), text, font=font, fill=text_color)

def _get_available_colors(epd):
    """Helper function to get available colors for the display"""
    colors = {
        'black': (getattr(epd, 'BLACK', 0x000000), (0, 0, 0)),
        'white': (getattr(epd, 'WHITE', 0xffffff), (255, 255, 255))
    }
    
    # Debug what the display actually has
    logger.debug(f"Display color values - BLACK: {epd.BLACK}, WHITE: {epd.WHITE}")
    if hasattr(epd, 'RED'):
        logger.debug(f"Display has RED attribute with value: {epd.RED}")
    if hasattr(epd, 'YELLOW'):
        logger.debug(f"Display has YELLOW attribute with value: {epd.YELLOW}")
    
    # Only add RED and YELLOW if they're actually different from BLACK and supported by the display
    if hasattr(epd, 'RED') and epd.RED != epd.BLACK and epd.RED != 0x00:
        colors['red'] = (epd.RED, (255, 0, 0))
    if hasattr(epd, 'YELLOW') and epd.YELLOW != epd.BLACK and epd.YELLOW != 0x00:
        colors['yellow'] = (epd.YELLOW, (255, 255, 0))
    
    logger.debug(f"Available colors for display: {list(colors.keys())}")
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
    # Use white text for dark backgrounds
    if primary_color == 'black' and ratio > 0.5:
        text_color = epd.WHITE if epd.is_bw_display else colors['white'][0]
    else:
        text_color = epd.BLACK if epd.is_bw_display else colors['black'][0]
    draw.text((text_x, text_y), text, font=font, fill=text_color)

def draw_vertical_lines_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Vertical line pattern - experimental"""
    colors = _get_available_colors(epd)
    if primary_color not in colors or secondary_color not in colors:
        logger.warning("Unsupported colors requested, falling back to black/white")
        primary_color = 'black'
        secondary_color = 'white'
    
    primary, _ = colors[primary_color]
    secondary, _ = colors[secondary_color]
    
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
    # Use white text for dark backgrounds
    text_color = colors['white'][0] if primary_color == 'black' and ratio > 0.5 else colors['black'][0]
    draw.text((text_x, text_y), text, font=font, fill=text_color)

def draw_diagonal_lines_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Diagonal line pattern - experimental"""
    colors = _get_available_colors(epd)
    if primary_color not in colors or secondary_color not in colors:
        logger.warning("Unsupported colors requested, falling back to black/white")
        primary_color = 'black'
        secondary_color = 'white'
    
    primary, _ = colors[primary_color]
    secondary, _ = colors[secondary_color]
    
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
    # Use white text for dark backgrounds
    text_color = colors['white'][0] if primary_color == 'black' and ratio > 0.5 else colors['black'][0]
    draw.text((text_x, text_y), text, font=font, fill=text_color)

def draw_dots_dither(draw, epd, x, y, width, height, text, primary_color, secondary_color, ratio, font):
    """Dot pattern - experimental"""
    colors = _get_available_colors(epd)
    if primary_color not in colors or secondary_color not in colors:
        logger.warning("Unsupported colors requested, falling back to black/white")
        primary_color = 'black'
        secondary_color = 'white'
    
    primary, _ = colors[primary_color]
    secondary, _ = colors[secondary_color]
    
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
    # Use white text for dark backgrounds
    text_color = colors['white'][0] if primary_color == 'black' and ratio > 0.5 else colors['black'][0]
    draw.text((text_x, text_y), text, font=font, fill=text_color) 


def draw_multicolor_dither(draw, epd, x, y, width, height, colors_with_ratios):
    """Draw a block using multiple colors with specified ratios using a checkerboard pattern"""
    # Only include colors that the display supports
    epd_colors = {
        'white': ((255, 255, 255), epd.WHITE),
        'black': ((0, 0, 0), epd.BLACK)
    }

    # Add RED if supported
    if hasattr(epd, 'RED'):
        epd_colors['red'] = ((255, 0, 0), epd.RED)

    # Add YELLOW if supported
    if hasattr(epd, 'YELLOW'):
        epd_colors['yellow'] = ((255, 255, 0), epd.YELLOW)

    # Filter out any colors that aren't supported by the display
    valid_colors = [(color, ratio) for color, ratio in colors_with_ratios if color in epd_colors]

    # If no valid colors remain, fallback to black and white
    if not valid_colors:
        valid_colors = [('black', 0.6), ('white', 0.4)]

    # Normalize ratios if we filtered out any colors
    total_ratio = sum(ratio for _, ratio in valid_colors)
    if total_ratio != 1.0:
        valid_colors = [(color, ratio/total_ratio) for color, ratio in valid_colors]

    # If only one color, fill the entire box with that color
    if len(valid_colors) == 1:
        color_name = valid_colors[0][0]
        draw.rectangle([x, y, x + width - 1, y + height - 1], fill=epd_colors[color_name][1])
        return

    # Create cumulative ratios for easier color selection
    cumulative_ratios = []
    cumsum = 0
    for color, ratio in valid_colors:
        cumsum += ratio
        cumulative_ratios.append((color, cumsum))

    # Count actual pixels of each color for verification
    color_counts = {color: 0 for color, _ in valid_colors}
    total_pixels = width * height

    # Create checkerboard pattern with offset rows
    for i in range(width):
        for j in range(height):
            # Offset every other row by one pixel
            offset = (j % 2) * 1
            # Use the offset in the pattern calculation
            pattern_value = ((i + offset + j) % 4) / 4.0

            # Add some controlled randomness to break up patterns while maintaining ratio
            noise = ((i * 37 + j * 17) % 7) / 28.0  # Pseudo-random noise between 0 and 0.25
            selection_value = (pattern_value + noise) % 1.0

            # Select color based on cumulative ratios
            chosen_color = valid_colors[-1][0]  # default to last color
            for color, cumulative_ratio in cumulative_ratios:
                if selection_value <= cumulative_ratio:
                    chosen_color = color
                    break

            # Update pixel count
            color_counts[chosen_color] += 1
            
            # Draw the pixel
            draw.point((x + i, y + j), fill=epd_colors[chosen_color][1])

    # Draw border in the dominant color
    primary_color = max(valid_colors, key=lambda x: x[1])[0]
    draw.rectangle([x, y, x + width - 1, y + height - 1], outline=epd_colors[primary_color][1])

    # Log actual ratios achieved
    for color, _ in valid_colors:
        actual_ratio = color_counts[color] / total_pixels
        logging.debug(f"Color {color}: target ratio = {dict(valid_colors)[color]:.2f}, actual ratio = {actual_ratio:.2f}")

def process_icon_for_epd(icon, epd):
    """Process icon using multi-color dithering"""
    width, height = icon.size

    # Create a new image with white background
    if epd.is_bw_display:
        processed = Image.new('1', icon.size, 1)  # 1 is white in 1-bit mode
    else:
        processed = Image.new('RGB', icon.size, epd.WHITE)
    draw = ImageDraw.Draw(processed)

    block_size = 4
    for x in range(0, width, block_size):
        for y in range(0, height, block_size):
            block = icon.crop((x, y, min(x + block_size, width), min(y + block_size, height)))

            # Calculate average color of non-transparent pixels
            r, g, b, valid_pixels = 0, 0, 0, 0
            for px in block.getdata():
                if len(px) == 4 and px[3] > 128:
                    r += px[0]
                    g += px[1]
                    b += px[2]
                    valid_pixels += 1

            if valid_pixels == 0:
                continue

            avg_color = (r//valid_pixels, g//valid_pixels, b//valid_pixels)

            # Get optimal color combination
            colors_with_ratios = find_optimal_colors(avg_color, epd)

            # Apply multi-color dithering
            draw_multicolor_dither(
                draw, epd,
                x, y,
                min(block_size, width - x),
                min(block_size, height - y),
                colors_with_ratios
            )

    return processed