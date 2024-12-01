import requests
import os
from datetime import datetime, timedelta
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
                'icon': weather_data['weather'][0]['icon'],
                'feels_like': round(weather_data['main']['feels_like']),
                'pressure': weather_data['main']['pressure']
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
            logger.debug(f"Current weather data: {current_data}")
            
            current = {
                'temperature': round(current_data['main']['temp']),
                'description': current_data['weather'][0]['main'],
                'humidity': current_data['main']['humidity'],
                'time': datetime.now().strftime('%H:%M'),
                'icon': current_data['weather'][0]['icon'],
                'sunrise': current_data['sys']['sunrise'],
                'sunset': current_data['sys']['sunset'],
                'pressure': current_data['main']['pressure'],
                'feels_like': round(current_data['main']['feels_like'])
            }

            # Get air quality
            air_quality = None
            if self.lat and self.lon:
                air_quality = self.get_air_quality()
                logger.debug(f"Air quality data: {air_quality}")
            
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
            
            logger.debug(f"Fetching forecast from URL: {url}")
            response = requests.get(url, params=params)
            response.raise_for_status()
            forecast_data = response.json()
            logger.debug(f"Received forecast data: {forecast_data}")
            
            try:
                # Get forecasts for next 3 days
                today = datetime.now().date()
                forecasts = []
                
                for day_offset in range(1, 4):  # Next 3 days
                    target_date = today + timedelta(days=day_offset)
                    day_forecasts = [
                        item for item in forecast_data['list'] 
                        if datetime.fromtimestamp(item['dt']).date() == target_date
                    ]
                    
                    if day_forecasts:
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
                    'is_daytime': sunrise < current_time < sunset,
                    'forecasts': forecasts,  # Add the 3-day forecast
                    'tomorrow': {
                        'min': forecasts[0]['min'] if forecasts else '--',
                        'icon': forecasts[0]['icon'] if forecasts else '',
                        'max': forecasts[0]['max'] if forecasts else '--',
                        'air_quality': air_quality
                    }
                }
                logger.debug(f"Processed weather result: {result}")
                return result
                
            except KeyError as ke:
                logger.error(f"Missing key in weather data: {ke}")
                logger.error(f"Weather data structure: {forecast_data}")
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