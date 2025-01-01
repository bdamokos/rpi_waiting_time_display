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
from functools import lru_cache
from weather.models import TemperatureUnit

logger = logging.getLogger(__name__)


show_sunshine = os.getenv('show_sunshine_hours', 'true').lower() == 'true'
show_precipitation = os.getenv('show_precipitation', 'true').lower() == 'true'

@lru_cache(maxsize=1000)
def load_svg_icon(svg_path: Path, size: Tuple[int, int], epd) -> Image.Image:
    """Load and resize an SVG icon.
    
    Size is a tuple of (width, height)
    """
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
                'pressure': weather_data.current.pressure,
                'daily_forecast': weather_data.daily_forecast
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

    def get_weather_data(self):
        """Get raw WeatherData object from provider."""
        if not self._backoff.should_retry():
            logger.warning(f"Skipping weather request, backing off until {self._backoff.get_retry_time_str()}")
            # Create error WeatherData object
            from weather.models import WeatherData, CurrentWeather, WeatherCondition
            return WeatherData(
                current=CurrentWeather(
                    temperature=0.0,
                    feels_like=0.0,
                    humidity=0,
                    pressure=0.0,
                    condition=WeatherCondition(
                        description=f"Retry at {self._backoff.get_retry_time_str()}",
                        icon="unknown"
                    )
                ),
                is_day=True
            )

        try:
            weather_data = self.provider.get_weather()
            self._backoff.update_backoff_state(True)
            return weather_data

        except Exception as e:
            self._backoff.update_backoff_state(False)
            logger.error(f"Error fetching weather: {e}")
            # Create error WeatherData object
            from weather.models import WeatherData, CurrentWeather, WeatherCondition
            return WeatherData(
                current=CurrentWeather(
                    temperature=0.0,
                    feels_like=0.0,
                    humidity=0,
                    pressure=0.0,
                    condition=WeatherCondition(
                        description="Error",
                        icon="unknown"
                    )
                ),
                is_day=True
            )

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
    unit_symbol = "°F" if weather_data.current.unit == TemperatureUnit.FAHRENHEIT else "°K" if weather_data.current.unit == TemperatureUnit.KELVIN else "°C"
    temp_text = f"{weather_data.current.temperature:.1f}{unit_symbol}"  # Show one decimal place

    # Calculate available space for temperature and icon using actual temperature text
    temp_bbox = draw.textbbox((0, 0), temp_text, font=font_xl)
    temp_width = temp_bbox[2] - temp_bbox[0]
    temp_height = temp_bbox[3] - temp_bbox[1]

    # Calculate icon size based on available space
    icon_width = Himage.width - temp_width - MARGIN-MARGIN-QR_SIZE
    icon_height = temp_height

    # Get weather icon
    icon_name = weather_data.current.condition.icon
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
        icon_y = MARGIN + (temp_height - icon_height) // 2 +3 # visually centre
        icon_x = Himage.width - MARGIN- QR_SIZE - icon_width
        logger.debug(f"Pasting icon at ({icon_x}, {icon_y})")
        Himage.paste(icon, (icon_x, icon_y))

    # Pre-calculate sun and moon info for positioning
    # Show either sunrise or sunset based on time of day
    if weather_data.is_day:
        sun_text = f" {weather_data.sunset.strftime('%H:%M')} "
        sun_icon_path = ICONS_DIR / "sun_set.svg"
    else:
        sun_text = f" {weather_data.sunrise.strftime('%H:%M')} "
        sun_icon_path = ICONS_DIR / "sun_rise.svg"

    moon_phase = get_moon_phase()
    moon_phase_emoji = moon_phase['emoji']
    moon_phase_name = f" {moon_phase['name'].lower()}"

    # Load and resize sun icon to match text height
    text_bbox = draw.textbbox((0, 0), sun_text, font=font_medium)
    text_height = text_bbox[3] - text_bbox[1]
    sun_icon = load_svg_icon(sun_icon_path, (text_height+5, text_height+5), epd)
    sun_icon_width = text_height if sun_icon else 0

    moon_phase_width = font_emoji.getbbox(f"{moon_phase_emoji}")[2] - font_emoji.getbbox(f"{moon_phase_emoji}")[0]
    sun_text_width = font_medium.getbbox(f"{sun_text}")[2] - font_medium.getbbox(f"{sun_text}")[0]
    moon_phase_text_width = font_medium.getbbox(f"{moon_phase_name}")[2] - font_medium.getbbox(f"{moon_phase_name}")[0]


    # Intermediate row if show_sunshine or show_precipitation
    

    # Calculate positions
    show_sunshine_or_precipitation_x_pos = MARGIN
    show_sunshine_or_precipitation_y_pos = 50
            
    # Load weather icons if needed
    sunshine_hours_icon = None
    umbrella_icon = None
            
    if show_sunshine:
        sunshine_duration = weather_data.daily_forecast[0].sunshine_duration
        sunshine_hours = sunshine_duration.total_seconds() / 3600
        sunshine_hours_icon = load_svg_icon(ICONS_DIR / "sun.svg", (20,20), epd)
        logger.debug(f"Sunshine duration for today: {sunshine_duration} ({sunshine_hours:.1f}h)")
            
        if show_precipitation:
            precipitation = weather_data.daily_forecast[0].precipitation_amount
            umbrella_icon = load_svg_icon(ICONS_DIR / "umbrella.svg", (20,20), epd)
            logger.debug(f"Precipitation for today: {precipitation:.1f}mm")
        
        # Calculate total width needed
        total_width_needed = 0
        if show_sunshine:
            sun_text = f"{sunshine_hours:.1f}h"
            sun_bbox = draw.textbbox((0, 0), sun_text, font=font_medium)
            sun_width = sun_bbox[2] - sun_bbox[0] + 20 + 2  # icon + text + spacing
            total_width_needed += sun_width + MARGIN
            
        if show_precipitation:
            rain_text = f"{precipitation:.1f}mm"
            rain_bbox = draw.textbbox((0, 0), rain_text, font=font_small)
            rain_width = rain_bbox[2] - rain_bbox[0] + 20 + 2  # icon + text + spacing
            total_width_needed += rain_width
        available_width = Himage.width - (2 * MARGIN)
            # Only draw if we have enough space
        if total_width_needed < available_width:
            # Draw sun icon and text if enabled
            if show_sunshine and sunshine_hours_icon:
                sun_text = f"{sunshine_hours:.1f}h"
                sun_bbox = draw.textbbox((0, 0), sun_text, font=font_medium)
                sun_width = sun_bbox[2] - sun_bbox[0]
                
                Himage.paste(sunshine_hours_icon, (show_sunshine_or_precipitation_x_pos, show_sunshine_or_precipitation_y_pos))
                draw.text((show_sunshine_or_precipitation_x_pos + 20 + 2, show_sunshine_or_precipitation_y_pos), sun_text, font=font_medium, fill=BLACK)
                sunrise_x_pos = show_sunshine_or_precipitation_x_pos
                show_sunshine_or_precipitation_x_pos += MARGIN + sun_icon_width + sun_text_width  # Add spacing after sun info
                
            # Draw umbrella icon and text if enabled
            if show_precipitation and umbrella_icon:
                rain_text = f"{precipitation:.1f}mm"
                Himage.paste(umbrella_icon, (show_sunshine_or_precipitation_x_pos - 4, show_sunshine_or_precipitation_y_pos))
                draw.text((show_sunshine_or_precipitation_x_pos + 20 + 2, show_sunshine_or_precipitation_y_pos), rain_text, font=font_medium, fill=BLACK)
                

    # Middle row: Next sun event (moved left and smaller)
    y_pos = 75 if show_sunshine or show_precipitation else 55



    # Draw sun info on left side with smaller font
    if sun_icon:
        Himage.paste(sun_icon, (MARGIN, y_pos))
    draw.text((sunrise_x_pos +20 + 2, y_pos), sun_text, font=font_medium, fill=BLACK)
    draw.text((MARGIN + sun_icon_width + sun_text_width, y_pos), moon_phase_emoji, font=font_emoji, fill=BLACK)
    draw.text((MARGIN + sun_icon_width + sun_text_width + moon_phase_width, y_pos), moon_phase_name, font=font_medium, fill=BLACK)

    # Bottom row: Three day forecast (today + next 2 days)
    forecast_y_pos = 100 if show_sunshine or show_precipitation else 85
    logger.debug(f"Forecasts: {weather_data.daily_forecast}")
    all_forecasts = weather_data.daily_forecast[:3]  # Start with up to 3 days
    logger.debug(f"Forecasts: {all_forecasts}")

    # Calculate available width - for forecasts we have full width
    available_width = Himage.width - (2 * MARGIN)  # Full width minus margins

    # Calculate how many forecasts we can actually fit by measuring each one
    forecasts = []
    total_width_needed = 0
    small_space = 5  # minimum spacing between icon and text
    big_space = small_space * 2  # spacing between forecast blocks

    for forecast in all_forecasts:
        # Calculate text width for this forecast
        unit_symbol = "°F" if forecast.unit == TemperatureUnit.FAHRENHEIT else "°K" if forecast.unit == TemperatureUnit.KELVIN else "°C"
        forecast_text = f"{round(forecast.min_temp)}-{round(forecast.max_temp)}{unit_symbol}"
        text_bbox = draw.textbbox((0, 0), forecast_text, font=font_medium)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        icon_width = int(text_height)  # Keep aspect ratio square

        # Calculate total width needed for this forecast block
        block_width = icon_width + small_space + text_width
        
        # Add big_space if this isn't the first forecast
        if forecasts:
            total_width_needed += big_space
            
        # Check if adding this forecast would exceed available width
        if total_width_needed + block_width > available_width:
            break
            
        total_width_needed += block_width
        forecasts.append(forecast)

    if not forecasts:
        logger.warning("Not enough space to display any forecasts")
        return

    logger.debug(f"Can fit {len(forecasts)} forecasts in {available_width}px width (total width needed: {total_width_needed}px)")

    # Calculate positions for all forecasts
    number_of_forecasts = len(forecasts)
    available_width = (Himage.width - (2*MARGIN))
    first_block_x = MARGIN
    available_width_after_first_block = available_width - MARGIN

    '''
    
    MARGIN ICON SPACE TEXT BIG_SPACE ICON SPACE TEXT BIG_SPACE ICON SPACE TEXT MARGIN
    
    '''
    # Calculate total width needed for all forecasts
    total_width_for_forecasts = 0
    icon_widths = []
    text_widths = []
    for forecast in forecasts:
        unit_symbol = "°F" if forecast.unit == TemperatureUnit.FAHRENHEIT else "°K" if forecast.unit == TemperatureUnit.KELVIN else "°C"
        forecast_text = f"{round(forecast.min_temp)}-{round(forecast.max_temp)}{unit_symbol}"
        text_bbox = draw.textbbox((0, 0), forecast_text, font=font_medium)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        icon_width = int(text_height)
        
        total_width_for_forecasts += icon_width + text_width
        icon_widths.append(icon_width)
        text_widths.append(text_width)

    total_width = Himage.width
    empty_space = total_width-total_width_for_forecasts
    empty_space_without_margins = empty_space - 2*MARGIN
    number_of_small_spaces = number_of_forecasts
    number_of_big_spaces = number_of_forecasts-1
    small_space = min(5, empty_space_without_margins/(number_of_small_spaces+number_of_big_spaces))
    big_space= small_space*2

    first_block_x = MARGIN
    first_icon_x = first_block_x
    first_text_x = first_icon_x + icon_widths[0] + small_space

    # Pre-calculate all positions
    block_start_positions = []
    icon_positions = []
    text_positions = []
    for i in range(number_of_forecasts):
        if i == 0:
            block_start_x = int(first_block_x)
            icon_x = int(first_icon_x)
            text_x = int(first_text_x)
        else:
            block_start_x = int(block_start_x + icon_widths[i-1] + text_widths[i-1] + big_space)
            icon_x = int(block_start_x)
            text_x = int(icon_x + icon_widths[i] + small_space)
        
        block_start_positions.append(block_start_x)
        icon_positions.append(icon_x)
        text_positions.append(text_x)

    for idx, forecast in enumerate(forecasts):
        # Calculate text size - round temperatures to whole numbers
        unit_symbol = "°F" if forecast.unit == TemperatureUnit.FAHRENHEIT else "°K" if forecast.unit == TemperatureUnit.KELVIN else "°C"
        forecast_text = f"{round(forecast.min_temp)}-{round(forecast.max_temp)}{unit_symbol}"
        text_bbox = draw.textbbox((0, 0), forecast_text, font=font_medium)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # Calculate icon size
        icon_width = int(text_height)  # Keep aspect ratio square and limit size
        icon_height = int(text_height)

        # Load and resize forecast icon
        icon_name = forecast.condition.icon
        icon_path = ICONS_DIR / f"{icon_name}.svg"
        if not icon_path.exists():
            logger.warning(f"Forecast icon not found: {icon_path}")
            icon_path = ICONS_DIR / "cloud.svg"  # fallback icon
        
        icon = load_svg_icon(icon_path, (icon_width, icon_height), epd)

        # Draw icon and text
        if icon:
            # Position icon slightly higher than text
            icon_y = int(forecast_y_pos + (text_height - icon_height) // 2 + 4)  # Added 4 pixels to move down more
            Himage.paste(icon, (icon_positions[idx], icon_y))
            draw.text((text_positions[idx], forecast_y_pos), 
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