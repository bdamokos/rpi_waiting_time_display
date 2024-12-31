#!/usr/bin/env python3
import os
from weather import OpenMeteoProvider
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def format_timedelta(td):
    """Format timedelta as hours and minutes"""
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return f"{hours}h {minutes}m"

def main():
    # Use environment variables or hardcoded test coordinates
    lat = float(os.getenv('Coordinates_LAT', '50.8505'))  # Brussels
    lon = float(os.getenv('Coordinates_LNG', '4.3488'))
    
    provider = OpenMeteoProvider(lat=lat, lon=lon)
    
    try:
        weather = provider.get_weather()
        
        # Print current weather
        print("\nCurrent Weather:")
        print(f"Temperature: {weather.current.temperature}°C")
        print(f"Feels like: {weather.current.feels_like}°C")
        print(f"Humidity: {weather.current.humidity}%")
        print(f"Condition: {weather.current.condition.description}")
        print(f"Icon: {weather.current.condition.icon}")
        
        # Print forecast
        print("\nForecast:")
        for forecast in weather.daily_forecast:
            print(f"\n{forecast.date.strftime('%Y-%m-%d')}:")
            print(f"  Min/Max: {forecast.min_temp}°C / {forecast.max_temp}°C")
            print(f"  Condition: {forecast.condition.description}")
            print(f"  Rain probability: {forecast.precipitation_probability}%")
            print(f"  Rain amount: {forecast.precipitation_amount}mm")
            print(f"  Sunshine duration: {format_timedelta(forecast.sunshine_duration)}")
        
        # Print sun times
        print("\nSun times:")
        print(f"Sunrise: {weather.sunrise.strftime('%H:%M')}")
        print(f"Sunset: {weather.sunset.strftime('%H:%M')}")
        print(f"Is daytime: {weather.is_day}")
        
        # Print attribution
        print(f"\n{weather.attribution}")
        
    except Exception as e:
        logger.error(f"Error getting weather: {e}")

if __name__ == "__main__":
    main() 