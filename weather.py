import requests
import os
from datetime import datetime
import dotenv
import qrcode
from io import BytesIO
import logging

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
            
            # Get forecast data
            if self.lat and self.lon:
                params = {
                    'lat': self.lat,
                    'lon': self.lon,
                    'appid': self.api_key,
                    'units': 'metric',
                    'cnt': 8  # Get next 24 hours (3-hour steps)
                }
            else:
                params = {
                    'q': f"{self.city},{self.country}",
                    'appid': self.api_key,
                    'units': 'metric',
                    'cnt': 8
                }
            
            response = requests.get(self.forecast_url, params=params)
            response.raise_for_status()
            forecast_data = response.json()
            
            # Process forecast data
            next_hours = []
            for item in forecast_data['list'][:3]:  # Get next 9 hours
                next_hours.append({
                    'time': datetime.fromtimestamp(item['dt']).strftime('%H:%M'),
                    'temp': round(item['main']['temp']),
                    'description': item['weather'][0]['main'],
                    'precipitation': item['pop'] * 100  # Probability of precipitation in %
                })
            logger.info(f"Forecast data: {next_hours}")
            return {
                'current': current,
                'forecast': next_hours,
                'humidity': current['humidity'],
                'feels_like': round(forecast_data['list'][0]['main']['feels_like']),
                'wind_speed': round(forecast_data['list'][0]['wind']['speed'] * 3.6),  # Convert m/s to km/h
                'precipitation_chance': round(forecast_data['list'][0]['pop'] * 100)
            }
            
        except Exception as e:
            logger.error(f"Error fetching detailed weather: {e}")
            return {
                'current': self.get_weather(),
                'forecast': [],
                'humidity': '--',
                'feels_like': '--',
                'wind_speed': '--',
                'precipitation_chance': '--'
            }

if __name__ == "__main__":
    # Test the module
    weather = WeatherService()
    print(weather.get_weather()) 