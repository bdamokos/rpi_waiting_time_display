from PIL import Image, ImageDraw, ImageFont
import requests
import os
from datetime import datetime, timedelta
import dotenv
import qrcode
from io import BytesIO
import logging
from dithering import process_icon_for_epd
from font_utils import get_font_paths
from display_adapter import return_display_lock
from astronomy_utils import get_moon_phase
import log_config
import json
import traceback
from pathlib import Path
from backoff import ExponentialBackoff
from weather.providers.factory import create_weather_provider
from weather.icons import WEATHER_ICONS, ICONS_DIR
import cairosvg
from typing import Tuple

logger = logging.getLogger(__name__)

def load_svg_icon(svg_path: Path, size: Tuple[int, int], epd) -> Image.Image:
    """Load and resize an SVG icon."""
    try:
        # Convert SVG to PNG in memory with transparency
        png_data = cairosvg.svg2png(
            url=str(svg_path),
            output_width=size[0],
            output_height=size[1],
            background_color="transparent"
        )
        
        # Create PIL Image from PNG data
        icon = Image.open(BytesIO(png_data))
        
        # Create a white background image
        if epd.is_bw_display:
            bg = Image.new('1', icon.size, 1)  # 1 = white
        else:
            bg = Image.new('RGB', icon.size, 'white')
            
        # Convert icon to RGBA to handle transparency
        icon = icon.convert('RGBA')
        
        # Paste the icon onto the white background using the alpha channel as mask
        bg.paste(icon, (0, 0), icon.split()[3])
        
        # Convert to final mode
        if epd.is_bw_display:
            bg = bg.convert('1')
        else:
            bg = bg.convert('RGB')
            
        logger.debug(f"Loaded SVG with mode: {bg.mode}, size: {bg.size}")
        return bg
    except Exception as e:
        logger.error(f"Error loading SVG icon {svg_path}: {e}")
        return None

DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))

CURRENT_ICON_SIZE = (46, 46)  # Size for current weather icon
FORECAST_ICON_SIZE = (28, 28)  # Smaller size for forecast icons

dotenv.load_dotenv(override=True)

display_lock = return_display_lock()

class WeatherService:
    def __init__(self):
        # Create weather provider
        provider_name = os.getenv('WEATHER_PROVIDER', 'openmeteo')
        self.provider = create_weather_provider(provider_name)
        logger.info(f"Using weather provider: {provider_name}")
        self._backoff = ExponentialBackoff()

    def get_air_quality(self):
        """Get current air quality data"""
        if not self._backoff.should_retry():
            logger.warning(f"Skipping air quality request, backing off until {self._backoff.get_retry_time_str()}")
            return None

        try:
            weather_data = self.provider.get_weather()
            self._backoff.update_backoff_state(True)
            if weather_data.air_quality:
                return {
                    'aqi': weather_data.air_quality.aqi,
                    'aqi_label': weather_data.air_quality.label,
                    'components': weather_data.air_quality.components
                }
            return None
            
        except Exception as e:
            self._backoff.update_backoff_state(False)
            logger.error(f"Error fetching air quality: {e}")
            return None

    def get_weather(self):
        if not self._backoff.should_retry():
            logger.warning(f"Skipping weather request, backing off until {self._backoff.get_retry_time_str()}")
            return {
                'temperature': '--',
                'description': f'Retry at {self._backoff.get_retry_time_str()}',
                'humidity': '--',
                'time': datetime.now().strftime('%H:%M'),
                'icon': 'unknown'
            }

        try:
            weather_data = self.provider.get_weather()
            self._backoff.update_backoff_state(True)
            
            return {
                'temperature': weather_data.current.temperature,
                'description': weather_data.current.condition.description,
                'humidity': weather_data.current.humidity,
                'time': datetime.now().strftime('%H:%M'),
                'icon': weather_data.current.condition.icon,
                'feels_like': weather_data.current.feels_like,
                'pressure': weather_data.current.pressure
            }

        except Exception as e:
            self._backoff.update_backoff_state(False)
            logger.error(f"Error fetching weather: {e}")
            return {
                'temperature': '--',
                'description': 'Error',
                'humidity': '--',
                'time': datetime.now().strftime('%H:%M'),
                'icon': 'unknown'
            }

    def get_detailed_weather(self):
        """Get current weather and forecast data"""
        if not self._backoff.should_retry():
            logger.warning(f"Skipping detailed weather request, backing off until {self._backoff.get_retry_time_str()}")
            return self._get_error_weather_data(f"Retry at {self._backoff.get_retry_time_str()}")

        try:
            weather_data = self.provider.get_weather()
            self._backoff.update_backoff_state(True)
            
            # Convert provider data to the format expected by the display
            current = {
                'temperature': weather_data.current.temperature,
                'description': weather_data.current.condition.description,
                'humidity': weather_data.current.humidity,
                'time': datetime.now().strftime('%H:%M'),
                'icon': weather_data.current.condition.icon,
                'sunrise': int(weather_data.sunrise.timestamp()),
                'sunset': int(weather_data.sunset.timestamp()),
                'pressure': weather_data.current.pressure,
                'feels_like': weather_data.current.feels_like,
                'temp_min': weather_data.daily_forecast[0].min_temp if weather_data.daily_forecast else None,
                'temp_max': weather_data.daily_forecast[0].max_temp if weather_data.daily_forecast else None
            }
            
            # Convert forecasts
            forecasts = []
            for forecast in weather_data.daily_forecast:
                forecasts.append({
                    'date': forecast.date.strftime('%Y-%m-%d'),
                    'min': forecast.min_temp,
                    'max': forecast.max_temp,
                    'condition': forecast.condition.description,
                    'icon': forecast.condition.icon
                })
            
            result = {
                'current': current,
                'humidity': current['humidity'],
                'wind_speed': 0,  # TODO: Add wind speed to provider models
                'sunrise': weather_data.sunrise.strftime('%H:%M'),
                'sunset': weather_data.sunset.strftime('%H:%M'),
                'temp_min': current['temp_min'],
                'temp_max': current['temp_max'],
                'is_daytime': weather_data.is_day,
                'forecasts': forecasts,
                'tomorrow': {
                    'min': forecasts[0]['min'] if forecasts else '',
                    'icon': forecasts[0]['icon'] if forecasts else '',
                    'max': forecasts[0]['max'] if forecasts else '',
                    'air_quality': {
                        'aqi': weather_data.air_quality.aqi,
                        'aqi_label': weather_data.air_quality.label,
                        'components': weather_data.air_quality.components
                    } if weather_data.air_quality else None
                }
            }
            return result
                
        except Exception as e:
            self._backoff.update_backoff_state(False)
            logger.error(f"Error fetching detailed weather: {e}", exc_info=True)
            return self._get_error_weather_data()

    def _get_error_weather_data(self, error_message="Error"):
        """Return default error data structure"""
        error_data = {
            'current': {
                'temperature': '--',
                'description': error_message,
                'humidity': '--',
                'time': datetime.now().strftime('%H:%M'),
                'icon': 'unknown'
            },
            'humidity': '--',
            'wind_speed': '--',
            'sunrise': '--:--',
            'sunset': '--:--',
            'is_daytime': True,  # Default to daytime on error
            'tomorrow': {
                'min': '--',
                'max': '--'
            },
            'air_quality': None
        }
        logger.debug(f"Returning error weather data: {error_data}")
        return error_data

if __name__ == "__main__":
    # Test the module
    weather = WeatherService()
    print(weather.get_weather()) 


# Constants
MARGIN = 5
QR_SIZE = 52  # QR code size in pixels
ICON_PADDING = 2  # Padding around icons

def draw_weather_display(epd, weather_data, last_weather_data=None, set_base_image=False):
    """Draw a weather-focused display when no bus times are available"""
    # Handle different color definitions - use simple 0/1 for BW mode
    if epd.is_bw_display:
        BLACK = 0
        WHITE = 1
        RED = 0
        YELLOW = 0
    else:
        BLACK = epd.BLACK
        WHITE = epd.WHITE
        RED = getattr(epd, 'RED', BLACK)
        YELLOW = getattr(epd, 'YELLOW', BLACK)

    # Create a new image with white background
    if epd.is_bw_display:
        Himage = Image.new('1', (epd.height, epd.width), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (epd.height, epd.width), WHITE)
        
    draw = ImageDraw.Draw(Himage)
    font_paths = get_font_paths()
    try:
        font_xl = ImageFont.truetype(font_paths['dejavu_bold'], 42)
        font_large = ImageFont.truetype(font_paths['dejavu_bold'], 28)
        font_medium = ImageFont.truetype(font_paths['dejavu'], 16)
        font_emoji = ImageFont.truetype(font_paths['emoji'], 16)
        font_small = ImageFont.truetype(font_paths['dejavu'], 14)
        font_tiny = ImageFont.truetype(font_paths['dejavu'], 10)
    except Exception as e:
        logger.error(f"Error loading fonts: {e}")
        font_xl = ImageFont.load_default()
        font_large = font_medium = font_small = font_tiny = font_emoji = font_xl

    # Top row: Large temperature and weather icon
    temp_text = f"{weather_data['current']['temperature']}°C"

    # Calculate available space for temperature and icon
    temp_bbox = draw.textbbox((0, 0), temp_text, font=font_xl)
    temp_width = temp_bbox[2] - temp_bbox[0]
    temp_height = temp_bbox[3] - temp_bbox[1]

    # Calculate icon size based on available space
    icon_width = min(temp_height, 46)  # Keep aspect ratio square and limit size
    icon_height = icon_width

    # Get weather icon
    icon_name = weather_data['current']['icon']
    icon_path = ICONS_DIR / f"{icon_name}.svg"
    logger.debug(f"Loading icon: {icon_name} from {icon_path}")
    if not icon_path.exists():
        logger.warning(f"Icon not found: {icon_path}")
        icon_path = ICONS_DIR / "cloud.svg"  # fallback icon
    
    # Load and resize icon
    icon = load_svg_icon(icon_path, (icon_width, icon_height), epd)
    
    # Draw temperature and icon
    draw.text((MARGIN, MARGIN), temp_text, font=font_xl, fill=BLACK, align="left")
    if icon:
        # Center icon vertically with text
        icon_y = MARGIN + (temp_height - icon_height) // 2
        icon_x = MARGIN + temp_width + 10
        logger.debug(f"Pasting icon at ({icon_x}, {icon_y})")
        Himage.paste(icon, (icon_x, icon_y))

    # Middle row: Next sun event (moved left and smaller)
    y_pos = 55

    # Show either sunrise or sunset based on time of day
    if weather_data['is_daytime']:
        sun_text = f" {weather_data['sunset']} "
        sun_icon_name = "sun"
    else:
        sun_text = f" {weather_data['sunrise']} "
        sun_icon_name = "moon"

    # Calculate sun/moon icon size based on text height
    sun_text_bbox = draw.textbbox((0, 0), sun_text, font=font_medium)
    sun_text_height = sun_text_bbox[3] - sun_text_bbox[1]
    sun_icon_size = sun_text_height

    # Load and draw sun/moon icon
    sun_icon_path = ICONS_DIR / f"{sun_icon_name}.svg"
    logger.debug(f"Loading sun/moon icon: {sun_icon_name} from {sun_icon_path}")
    sun_icon = load_svg_icon(sun_icon_path, (sun_icon_size, sun_icon_size), epd)

    moon_phase = get_moon_phase()
    moon_phase_name = f" {moon_phase['name'].lower()}"

    # Draw sun info
    if sun_icon:
        # Center icon vertically with text
        sun_icon_y = y_pos + (sun_text_height - sun_icon_size) // 2
        Himage.paste(sun_icon, (MARGIN, sun_icon_y))
        sun_icon_width = sun_icon_size
    else:
        sun_icon_width = 0

    draw.text((MARGIN + sun_icon_width + 5, y_pos), sun_text, font=font_medium, fill=BLACK)
    draw.text((MARGIN + sun_icon_width + 5 + font_medium.getbbox(sun_text)[2], y_pos), 
              moon_phase_name, font=font_medium, fill=BLACK)

    # Bottom row: Three day forecast (today + next 2 days)
    forecast_y_pos = 85
    logger.debug(f"Forecasts: {weather_data['forecasts']}")
    forecasts = weather_data['forecasts'][:3]
    logger.debug(f"Forecasts: {forecasts}")

    # Calculate available width for each forecast block
    available_width = Himage.width - (2 * MARGIN)
    forecast_block_width = available_width // 3

    for idx, forecast in enumerate(forecasts):
        # Calculate text size
        forecast_text = f"{forecast['min']}-{forecast['max']}°"
        text_bbox = draw.textbbox((0, 0), forecast_text, font=font_medium)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # Calculate icon size
        icon_width = min(text_height, 28)  # Keep aspect ratio square and limit size
        icon_height = icon_width

        # Load and resize forecast icon
        icon_name = forecast['icon']
        icon_path = ICONS_DIR / f"{icon_name}.svg"
        if not icon_path.exists():
            logger.warning(f"Forecast icon not found: {icon_path}")
            icon_path = ICONS_DIR / "cloud.svg"  # fallback icon
        
        icon = load_svg_icon(icon_path, (icon_width, icon_height), epd)

        # Calculate block position
        current_x = MARGIN + (idx * forecast_block_width)
        block_center_x = current_x + (forecast_block_width - (icon_width + 5 + text_width)) // 2

        # Draw icon and text
        if icon:
            # Center icon vertically with text
            icon_y = forecast_y_pos + (text_height - icon_height) // 2
            Himage.paste(icon, (block_center_x, icon_y))
            draw.text((block_center_x + icon_width + 5, forecast_y_pos), 
                     forecast_text, font=font_medium, fill=BLACK)

    # Generate and draw QR code (larger size)
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    qr_code_address = os.getenv("weather_mode_qr_code_address", "http://raspberrypi.local:5002/debug")
    qr.add_data(qr_code_address)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')

    # Scale QR code to defined size
    qr_img = qr_img.resize((QR_SIZE, QR_SIZE))
    qr_x = Himage.width - QR_SIZE - MARGIN
    qr_y = MARGIN
    Himage.paste(qr_img, (qr_x, qr_y))

    # Draw time under QR code
    current_time = datetime.now().strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_tiny)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = Himage.width - time_width - MARGIN
    time_y = Himage.height - time_bbox[3]- (MARGIN // 2)
    draw.text((time_x, time_y),
              current_time, font=font_tiny, fill=BLACK, align="right")

    # Draw a border around the display
    # border_color = getattr(epd, 'RED', epd.BLACK)  # Fall back to BLACK if RED not available
    # draw.rectangle([(0, 0), (Himage.width-1, Himage.height-1)], outline=border_color)

    # Rotate the image 90 degrees
    Himage = Himage.rotate(DISPLAY_SCREEN_ROTATION, expand=True)

    with display_lock:
        # Display the image
        buffer = epd.getbuffer(Himage)
        if hasattr(epd, 'displayPartial'):
            if set_base_image:
                logger.debug("Setting base image for weather display mode")
                epd.init()
                epd.displayPartBaseImage(buffer)
            else:
                logger.debug("Using partial display update for weather info")
                epd.displayPartial(buffer)
        else:
            logger.debug("Using full display update for weather info")
            epd.display(buffer)