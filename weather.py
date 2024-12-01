import requests
import os
from datetime import datetime
import dotenv
import qrcode
from io import BytesIO
import logging
import log_config

logger = logging.getLogger(__name__)



dotenv.load_dotenv()
weather_api_key = os.getenv('OPENWEATHER_API_KEY')
coordinates_lat = os.getenv('Coordinates_LAT')
coordinates_lng = os.getenv('Coordinates_LNG')
city = os.getenv('City')
country = os.getenv('Country')



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
    def get_air_quality(self):
        """Get current air quality data"""
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
            
            return {
                'aqi': aqi,
                'aqi_label': self.aqi_labels.get(aqi, "Unknown"),
                'components': components
            }
            
        except Exception as e:
            logger.error(f"Error fetching air quality: {e}")
            return None
        
    def get_weather(self):
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
            return {
                'temperature': round(weather_data['main']['temp']),
                'description': weather_data['weather'][0]['main'],
                'humidity': weather_data['main']['humidity'],
                'time': datetime.now().strftime('%H:%M'),
                'icon': weather_data['weather'][0]['icon']
            }
            
        except Exception as e:
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
        try:
            # Get current weather
            current = self.get_weather()
            logger.debug(f"Current weather data: {current}")
            
            # Get air quality
            air_quality = None
            if self.lat and self.lon:
                air_quality = self.get_air_quality()
                logger.debug(f"Air quality data: {air_quality}")
            
            # Get daily forecast and sun data
            if self.lat and self.lon:
                params = {
                    'lat': self.lat,
                    'lon': self.lon,
                    'appid': self.api_key,
                    'units': 'metric',
                    'exclude': 'minutely,hourly,alerts'
                }
                url = "http://api.openweathermap.org/data/3.0/onecall"
            else:
                params = {
                    'q': f"{self.city},{self.country}",
                    'appid': self.api_key,
                    'units': 'metric'
                }
                url = self.base_url
            
            logger.debug(f"Fetching detailed weather from URL: {url}")
            response = requests.get(url, params=params)
            response.raise_for_status()
            weather_data = response.json()
            logger.debug(f"Received weather data: {weather_data}")
            
            try:
                # Convert sunrise/sunset to local time
                sunrise = datetime.fromtimestamp(weather_data['current']['sunrise'])
                sunset = datetime.fromtimestamp(weather_data['current']['sunset'])
                current_time = datetime.now()
                
                # Get tomorrow's forecast
                tomorrow = weather_data['daily'][1]
                
                result = {
                    'current': current,
                    'humidity': current['humidity'],
                    'wind_speed': round(weather_data['current']['wind_speed'] * 3.6),
                    'sunrise': sunrise.strftime('%H:%M'),
                    'sunset': sunset.strftime('%H:%M'),
                    'is_daytime': sunrise < current_time < sunset,
                    'tomorrow': {
                        'min': round(tomorrow['temp']['min']),
                        'max': round(tomorrow['temp']['max']),
                        'air_quality': air_quality
                    }
                }
                logger.debug(f"Processed weather result: {result}")
                return result
                
            except KeyError as ke:
                logger.error(f"Missing key in weather data: {ke}")
                logger.error(f"Weather data structure: {weather_data}")
                raise
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error fetching detailed weather: {e}")
            return self._get_error_weather_data()
        except Exception as e:
            logger.error(f"Error fetching detailed weather: {e}", exc_info=True)
            return self._get_error_weather_data()

    def _get_error_weather_data(self):
        """Return default error data structure"""
        error_data = {
            'current': self.get_weather(),  # This has its own error handling
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