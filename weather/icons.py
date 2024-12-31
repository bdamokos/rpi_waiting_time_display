"""Weather icons and icon mapping."""

from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

# Icon paths
ICONS_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "icons"
CACHE_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "cache" / "icons"

# Weather icon mapping (Font Awesome icon names to emoji)
WEATHER_ICONS = {
    'sun': '☀',
    'cloud-sun': '⛅',
    'cloud': '☁',
    'cloud-rain': '🌧',
    'cloud-showers-heavy': '🌧',
    'cloud-showers-water': '🌧',
    'snowflake': '❄',
    'cloud-bolt': '⚡',
    'cloud-meatball': '⚡',
    'cloud-sun-rain': '🌦',
    'cloud-moon': '🌙',
    'cloud-moon-rain': '🌧',
    'moon': '🌙',
    'unknown': '?',
} 