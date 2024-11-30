import requests
import os
from datetime import datetime
import dotenv

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
            
            return {
                'temperature': round(weather_data['main']['temp']),
                'description': weather_data['weather'][0]['main'],
                'humidity': weather_data['main']['humidity'],
                'time': datetime.now().strftime('%H:%M'),
                'icon': weather_data['weather'][0]['icon']
            }
            
        except Exception as e:
            print(f"Error fetching weather: {e}")
            return {
                'temperature': '--',
                'description': 'Error',
                'humidity': '--',
                'time': datetime.now().strftime('%H:%M'),
                'icon': 'unknown'
            }

if __name__ == "__main__":
    # Test the module
    weather = WeatherService()
    print(weather.get_weather()) 