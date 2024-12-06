# font_utils.py
"""
Utility functions for working with fonts

Usage:
python font_utils.py


"""

from PIL import ImageFont
import unicodedata
import logging
from log_config import logger
import os

def test_font_character(font_path: str, char: str, size: int = 24) -> bool:
    """
    Test if a font supports a specific character.
    
    Args:
        font_path: Path to the font file
        char: Character to test
        size: Font size to use for testing
    
    Returns:
        bool: True if the font supports the character, False otherwise
    """
    try:
        # Load the font
        font = ImageFont.truetype(font_path, size)
        font_short_name = os.path.basename(font_path)
        
        # Get the character name for logging
        char_name = unicodedata.name(char, "UNKNOWN")
        
        # Try to get the glyph metrics
        bbox = font.getbbox(char)
        
        # If bbox is None or has zero width/height, the character isn't supported
        if not bbox or (bbox[2] - bbox[0] == 0) or (bbox[3] - bbox[1] == 0):
            logger.debug(f"Font {font_short_name} does not support '{char}' ({char_name})")
            return False
            
        logger.debug(f"Font {font_short_name} supports '{char}' ({char_name})")
        return True
        
    except Exception as e:
        logger.error(f"Error testing font {font_short_name} for character '{char}': {e}")
        return False



# Add to weather.py or where your weather icons are defined
WEATHER_ICONS = {
    'Clear': '☀',
    'Clouds': '☁',
    'Rain': '🌧',
    'Snow': '❄',
    'Thunderstorm': '⚡',
    'Drizzle': '🌦',
    'Mist': '🌫',
}

def verify_font_support():
    """Verify that the current font supports all weather icons"""
    font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
    unsupported = []
    
    for weather, icon in WEATHER_ICONS.items():
        if not test_font_character(font_path, icon):
            unsupported.append((weather, icon))
    
    if unsupported:
        logger.warning(f"Current font does not support these weather icons: {unsupported}")
        logger.warning("Consider installing fonts-noto-color-emoji for better support")
    
    return len(unsupported) == 0

if __name__ == "__main__":
    verify_font_support()
    # Example usage:
    test_chars = ['🕒', '⚡', '☀', '☁', '🌧', '❄', '⚡', '🌦', '🌫']
    font_paths = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        # '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf',
        # Add other font paths to test
    ]

    for font_path in font_paths:
        print(f"\nTesting font: {font_path}")
        for char in test_chars:
            supported = test_font_character(font_path, char)
            print(f"Character {char}: {'✓' if supported else '✗'}")