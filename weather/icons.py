"""Weather icons and icon mapping."""

from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)

# Icon paths
ICONS_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "icons"
CACHE_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "cache" / "icons"

# Weather icon mapping
WEATHER_ICONS = {
    'Clear': '☀',
    'Clouds': '☁',
    'Rain': '🌧',
    'Snow': '❄',
    'Thunderstorm': '⚡',
    'Drizzle': '🌦',
    'Mist': '🌫',
    'Fog': '🌫',
} 