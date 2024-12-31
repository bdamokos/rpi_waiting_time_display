from PIL import Image
import cairosvg
from io import BytesIO
import os
from pathlib import Path
import logging
from dithering import process_icon_for_epd

logger = logging.getLogger(__name__)

ICONS_DIR = Path(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))) / "weather_icons"
CACHE_DIR = Path(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))) / "cache" / "weather_icons"

def load_weather_icon(icon_name: str, size: tuple[int, int], epd) -> Image.Image:
    """Load and process a weather icon from the Font Awesome SVG files"""
    try:
        # Create cache directory if it doesn't exist
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Generate cache filename based on icon name and size
        cache_file = CACHE_DIR / f"{icon_name}_{size[0]}x{size[1]}.png"
        
        # Check if cached version exists
        if cache_file.exists():
            icon = Image.open(cache_file)
            processed_icon = process_icon_for_epd(icon, epd)
            return processed_icon
            
        # If not in cache, load and process SVG
        svg_path = ICONS_DIR / f"{icon_name}.svg"
        if not svg_path.exists():
            logger.warning(f"Icon {icon_name} not found, using default")
            svg_path = ICONS_DIR / "cloud.svg"
            
        # Convert SVG to PNG using cairosvg
        png_data = cairosvg.svg2png(
            url=str(svg_path),
            output_width=size[0],
            output_height=size[1]
        )
        
        # Create PIL Image from PNG data
        icon = Image.open(BytesIO(png_data))
        
        # Save to cache
        icon.save(cache_file, "PNG")
        
        # Process for EPD
        processed_icon = process_icon_for_epd(icon, epd)
        return processed_icon
        
    except Exception as e:
        logger.error(f"Error loading weather icon {icon_name}: {e}")
        return None 