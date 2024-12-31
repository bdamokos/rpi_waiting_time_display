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

logger = logging.getLogger(__name__)

WEATHER_ICON_URL = "https://openweathermap.org/img/wn/{}@4x.png"
CACHE_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "cache" / "icons"
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


def get_weather_icon(icon_code, size, epd):
    """Fetch and process weather icon from OpenWeatherMap with caching"""
    try:
        # Create cache directory if it doesn't exist
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

        # Generate cache filename based on icon code and size
        cache_file = CACHE_DIR / f"icon_{icon_code}_{size[0]}x{size[1]}.png"

        # Check if cached version exists
        if cache_file.exists():
            # logger.debug(f"Loading cached icon: {cache_file}")
            icon = Image.open(cache_file)

            # Process the cached icon
            processed_icon = process_icon_for_epd(icon, epd)
            return processed_icon

        # If not in cache, download and process
        logger.debug(f"Downloading icon: {icon_code}")
        response = requests.get(WEATHER_ICON_URL.format(icon_code))
        if response.status_code == 200:
            icon = Image.open(BytesIO(response.content))
            icon = icon.resize(size, Image.Resampling.LANCZOS)

            # Save to cache
            icon.save(cache_file, "PNG")
            # logger.debug(f"Saved icon to cache: {cache_file}")

            # Process the icon
            processed_icon = process_icon_for_epd(icon, epd)
            return processed_icon

    except Exception as e:
        logger.error(f"Error processing weather icon: {e}\n{traceback.format_exc()}")
    return None


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


def draw_weather_display(epd, weather_data, last_weather_data=None, set_base_image=False):
    """Draw a weather-focused display when no bus times are available"""
    # Handle different color definitions
    BLACK = epd.BLACK
    WHITE = epd.WHITE
    RED = getattr(epd, 'RED', BLACK)  # Fall back to BLACK if RED not available
    YELLOW = getattr(epd, 'YELLOW', BLACK)  # Fall back to BLACK if YELLOW not available

    # Create a new image with white background
    if epd.is_bw_display:
        Himage = Image.new('1', (epd.height, epd.width), 1)  # 1 is white in 1-bit mode
    else:
        Himage = Image.new('RGB', (epd.height, epd.width), WHITE)

    # 250x120 width x height
    draw = ImageDraw.Draw(Himage)
    font_paths = get_font_paths()
    try:
        font_xl = ImageFont.truetype(font_paths['dejavu_bold'], 42)
        font_large = ImageFont.truetype(font_paths['dejavu_bold'], 28)
        font_medium = ImageFont.truetype(font_paths['dejavu'], 16)
        font_emoji = ImageFont.truetype(font_paths['emoji'], 16)
        font_small = ImageFont.truetype(font_paths['dejavu'], 14)
        font_tiny = ImageFont.truetype(font_paths['dejavu'], 10)
    except:
        font_xl = ImageFont.load_default()
        font_large = font_medium = font_small = font_tiny = font_xl

    MARGIN = 5

    # Top row: Large temperature and weather icon
    temp_text = f"{weather_data['current']['temperature']}°C"

    # Get and draw weather icon
    icon = get_weather_icon(weather_data['current']['icon'], CURRENT_ICON_SIZE, epd)

    # Center temperature and icon
    temp_bbox = draw.textbbox((0, 0), temp_text, font=font_xl)
    temp_width = temp_bbox[2] - temp_bbox[0]

    total_width = temp_width + CURRENT_ICON_SIZE[0] + 65
    # start_x = (Himage.width - total_width) // 2
    start_x = MARGIN

    # Draw temperature
    draw.text((start_x, MARGIN), temp_text, font=font_xl, fill=epd.BLACK, align="left")

    # Draw icon
    if icon:
        icon_x = start_x + temp_width + 20
        icon_y = MARGIN
        Himage.paste(icon, (icon_x, icon_y))
    else:
        # Fallback to text icon if image loading fails
        weather_icon = WEATHER_ICONS.get(weather_data['current']['description'], '?')
        draw.text((start_x + temp_width + 20, MARGIN), weather_icon,
                  font=font_xl, fill=epd.BLACK)

    # Middle row: Next sun event (moved left and smaller)
    y_pos = 55

    # Show either sunrise or sunset based on time of day
    if weather_data['is_daytime']:
        sun_text = f" {weather_data['sunset']} "
        sun_icon = "☀"
    else:
        sun_text = f" {weather_data['sunrise']} "
        sun_icon = "☀"
    moon_phase = get_moon_phase()
    moon_phase_emoji = moon_phase['emoji']
    moon_phase_name = f" {moon_phase['name'].lower()}"
    sun_icon_width = font_emoji.getbbox(f"{sun_icon}")[2] - font_emoji.getbbox(f"{sun_icon}")[0]
    moon_phase_width = font_emoji.getbbox(f"{moon_phase_emoji}")[2] - font_emoji.getbbox(f"{moon_phase_emoji}")[0]
    sun_text_width = font_medium.getbbox(f"{sun_text}")[2] - font_medium.getbbox(f"{sun_text}")[0]
    moon_phase_text_width = font_medium.getbbox(f"{moon_phase_name}")[2] - font_medium.getbbox(f"{moon_phase_name}")[0]
    # Draw sun info on left side with smaller font
    sun_full = f"{sun_icon} {sun_text} {moon_phase_emoji} {moon_phase_name}"
    draw.text((MARGIN , y_pos), sun_icon, font=font_emoji, fill=epd.BLACK)
    draw.text((MARGIN + sun_icon_width, y_pos), sun_text, font=font_medium, fill=epd.BLACK)
    draw.text((MARGIN + sun_icon_width + sun_text_width, y_pos), moon_phase_emoji, font=font_emoji, fill=epd.BLACK)
    draw.text((MARGIN + sun_icon_width + sun_text_width + moon_phase_width, y_pos), moon_phase_name, font=font_medium, fill=epd.BLACK)

    # Bottom row: Three day forecast (today + next 2 days)
    y_pos = 85
    logger.debug(f"Forecasts: {weather_data['forecasts']}")
    forecasts = weather_data['forecasts'][:3]
    logger.debug(f"Forecasts: {forecasts}")

    # Calculate available width
    available_width = Himage.width - (2 * MARGIN)
    # Width for each forecast block (icon + temp)
    forecast_block_width = available_width // 3

    for idx, forecast in enumerate(forecasts):
        # Calculate starting x position for this forecast block
        current_x = MARGIN + (idx * forecast_block_width)

        # Get and draw icon
        icon = get_weather_icon(forecast['icon'], FORECAST_ICON_SIZE, epd)
        if icon:
            # Center icon and text within their block
            forecast_text = f"{forecast['min']}-{forecast['max']}°"
            text_bbox = draw.textbbox((0, 0), forecast_text, font=font_medium)
            text_width = text_bbox[2] - text_bbox[0]
            total_element_width = FORECAST_ICON_SIZE[0] + 5 + text_width

            # Center the whole block
            block_start_x = current_x + (forecast_block_width - total_element_width) // 2

            # Draw icon and text
            icon_y = y_pos + (font_medium.size - FORECAST_ICON_SIZE[1]) // 2
            Himage.paste(icon, (block_start_x, icon_y))

            # Draw temperature
            text_x = block_start_x + FORECAST_ICON_SIZE[0] + 3
            draw.text((text_x, y_pos), forecast_text, font=font_medium, fill=epd.BLACK)

    # Generate and draw QR code (larger size)
    qr = qrcode.QRCode(version=1, box_size=2, border=1)
    qr_code_address = os.getenv("weather_mode_qr_code_address", "http://raspberrypi.local:5002/debug")
    qr.add_data(qr_code_address)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    qr_img = qr_img.convert('RGB')

    # Scale QR code to larger size
    qr_size = 52
    qr_img = qr_img.resize((qr_size, qr_size))
    qr_x = Himage.width - qr_size - MARGIN
    qr_y = MARGIN
    Himage.paste(qr_img, (qr_x, qr_y))

    # Draw time under QR code
    current_time = datetime.now().strftime("%H:%M")
    time_bbox = draw.textbbox((0, 0), current_time, font=font_tiny)
    time_width = time_bbox[2] - time_bbox[0]
    time_x = Himage.width - time_width - MARGIN
    time_y = Himage.height - time_bbox[3]- (MARGIN // 2)
    draw.text((time_x, time_y),
              current_time, font=font_tiny, fill=epd.BLACK, align="right")

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