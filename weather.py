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

logger = logging.getLogger(__name__)

WEATHER_ICON_URL = "https://openweathermap.org/img/wn/{}@4x.png"
CACHE_DIR = Path(os.path.dirname(os.path.realpath(__file__))) / "cache" / "weather_icons"
DISPLAY_SCREEN_ROTATION = int(os.getenv('screen_rotation', 90))

CURRENT_ICON_SIZE = (46, 46)  # Size for current weather icon
FORECAST_ICON_SIZE = (28, 28)  # Smaller size for forecast icons

dotenv.load_dotenv(override=True)
weather_api_key = os.getenv('OPENWEATHER_API_KEY')
coordinates_lat = os.getenv('Coordinates_LAT')
coordinates_lng = os.getenv('Coordinates_LNG')
city = os.getenv('City')
country = os.getenv('Country')

display_lock = return_display_lock()

class WeatherService:
    def __init__(self):
        self.api_key = weather_api_key
        self.lat = coordinates_lat
        self.lon = coordinates_lng
        self.city = city
        self.country = country
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"
        self.forecast_url = "http://api.openweathermap.org/data/2.5/forecast"
        self.air_pollution_url = "http://api.openweathermap.org/data/2.5/air_pollution"
        self.aqi_labels = {
            1: "Good",
            2: "Fair",
            3: "Moderate",
            4: "Poor",
            5: "Very Poor"
        }
        self._backoff = ExponentialBackoff()

    def get_air_quality(self):
        """Get current air quality data"""
        if not self._backoff.should_retry():
            logger.warning(f"Skipping air quality request, backing off until {self._backoff.get_retry_time_str()}")
            return None

        try:
            if not (self.lat and self.lon):
                return None

            params = {
                'lat': self.lat,
                'lon': self.lon,
                'appid': self.api_key
            }
            
            response = requests.get(self.air_pollution_url, params=params)
            response.raise_for_status()
            data = response.json()
            
            aqi = data['list'][0]['main']['aqi']
            components = data['list'][0]['components']
            
            self._backoff.update_backoff_state(True)
            return {
                'aqi': aqi,
                'aqi_label': self.aqi_labels.get(aqi, "Unknown"),
                'components': components
            }
            
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
            if self.lat and self.lon:
                params = {
                    'lat': self.lat,
                    'lon': self.lon,
                    'appid': self.api_key,
                    'units': 'metric'  # For Celsius
                }
            elif self.city and self.country:
                params = {
                    'q': f"{self.city},{self.country}",
                    'appid': self.api_key,
                    'units': 'metric'  # For Celsius
                }
            else:
                raise ValueError("Either coordinates or city and country must be provided")
            
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            
            weather_data = response.json()
            logger.info(f"Weather data: {weather_data}")

            self._backoff.update_backoff_state(True)
            return {
                'temperature': round(weather_data['main']['temp']),
                'description': weather_data['weather'][0]['main'],
                'humidity': weather_data['main']['humidity'],
                'time': datetime.now().strftime('%H:%M'),
                'icon': weather_data['weather'][0]['icon'],
                'feels_like': round(weather_data['main']['feels_like']),
                'pressure': weather_data['main']['pressure']
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
            # Get current weather with sunrise/sunset
            if self.lat and self.lon:
                params = {
                    'lat': self.lat,
                    'lon': self.lon,
                    'appid': self.api_key,
                    'units': 'metric'
                }
            else:
                params = {
                    'q': f"{self.city},{self.country}",
                    'appid': self.api_key,
                    'units': 'metric'
                }
            
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()
            current_data = response.json()
            
            current = {
                'temperature': round(current_data['main']['temp']),
                'description': current_data['weather'][0]['main'],
                'humidity': current_data['main']['humidity'],
                'time': datetime.now().strftime('%H:%M'),
                'icon': current_data['weather'][0]['icon'],
                'sunrise': current_data['sys']['sunrise'],
                'sunset': current_data['sys']['sunset'],
                'pressure': current_data['main']['pressure'],
                'feels_like': round(current_data['main']['feels_like']),
                'temp_min': round(current_data['main']['temp_min']),
                'temp_max': round(current_data['main']['temp_max'])
            }

            # Get air quality
            air_quality = None
            if self.lat and self.lon:
                air_quality = self.get_air_quality()
            
            # Get forecast data for next 3 days using 5 day/3 hour forecast API
            if self.lat and self.lon:
                params = {
                    'lat': self.lat,
                    'lon': self.lon,
                    'appid': self.api_key,
                    'units': 'metric'
                }
                url = self.forecast_url
            else:
                params = {
                    'q': f"{self.city},{self.country}",
                    'appid': self.api_key,
                    'units': 'metric'
                }
                url = self.forecast_url
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            forecast_data = response.json()

            try:
                # Get forecasts for next 3 days
                today = datetime.now().date()
                forecasts = []

                for day_offset in range(0, 4):  # Next 3 days
                    target_date = today + timedelta(days=day_offset)
                    
                    day_forecasts = [
                        item for item in forecast_data['list'] 
                        if datetime.fromtimestamp(item['dt']).date() == target_date
                    ]
                    
                    if day_forecasts:
                        first_item_dt = datetime.fromtimestamp(day_forecasts[0]['dt'])
                        last_item_dt = datetime.fromtimestamp(day_forecasts[-1]['dt'])
                        logger.debug(f"Forecast range for {target_date}: from {first_item_dt.strftime('%H:%M')} to {last_item_dt.strftime('%H:%M')}. {len(day_forecasts)} items.")
                        min_temp = min(float(item['main']['temp_min']) for item in day_forecasts)
                        max_temp = max(float(item['main']['temp_max']) for item in day_forecasts)
                        icon = day_forecasts[0]['weather'][0]['icon']
                        # Get the most common weather condition for the day
                        conditions = [item['weather'][0]['main'] for item in day_forecasts]
                        condition = max(set(conditions), key=conditions.count)
                        
                        forecasts.append({
                            'date': target_date.strftime('%Y-%m-%d'),
                            'min': round(min_temp),
                            'max': round(max_temp),
                            'condition': condition,
                            'icon': icon
                        })
                


                # Get sunrise/sunset from current weather data
                sunrise = datetime.fromtimestamp(current.get('sunrise', 0))
                sunset = datetime.fromtimestamp(current.get('sunset', 0))
                current_time = datetime.now()
                
                result = {
                    'current': current,
                    'humidity': current.get('humidity', '--'),
                    'wind_speed': round(float(current_data.get('wind', {}).get('speed', 0)) * 3.6),  # Convert m/s to km/h
                    'sunrise': datetime.fromtimestamp(current['sunrise']).strftime('%H:%M'),
                    'sunset': datetime.fromtimestamp(current['sunset']).strftime('%H:%M'),
                    'temp_min': current.get('temp_min', ''),
                    'temp_max': current.get('temp_max', ''),
                    'is_daytime': sunrise < current_time < sunset,
                    'forecasts': forecasts,  # Add the 3-day forecast
                    'tomorrow': {
                        'min': forecasts[0]['min'] if forecasts else '',
                        'icon': forecasts[0]['icon'] if forecasts else '',
                        'max': forecasts[0]['max'] if forecasts else '',
                        'air_quality': air_quality
                    }
                }
                # logger.debug(f"Processed weather result: {result}")
                return result
                
            except KeyError as ke:
                logger.error(f"Missing key in weather data: {ke}")
                logger.error(f"Weather data structure: {forecast_data}")
                raise
                
        except requests.exceptions.RequestException as e:
            self._backoff.update_backoff_state(False)
            logger.error(f"Network error fetching detailed weather: {e}")
            return self._get_error_weather_data()
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


def draw_weather_display(epd, weather_data, last_weather_data=None):
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
        epd.display(buffer)