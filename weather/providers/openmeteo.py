import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
from .base import WeatherProvider
from ..models import (
    WeatherData,
    CurrentWeather,
    WeatherCondition,
    DailyForecast,
    AirQuality,
    TemperatureUnit,
)

logger = logging.getLogger(__name__)

# Weather code mapping to Font Awesome icons
WEATHER_CODES: Dict[int, Dict[str, str]] = {
    0: {"description": "Clear sky", "icon": "sun"},
    1: {"description": "Mainly clear", "icon": "cloud-sun"},
    2: {"description": "Partly cloudy", "icon": "cloud-sun"},
    3: {"description": "Overcast", "icon": "cloud"},
    45: {"description": "Foggy", "icon": "cloud"},
    48: {"description": "Depositing rime fog", "icon": "cloud"},
    51: {"description": "Light drizzle", "icon": "cloud-rain"},
    53: {"description": "Moderate drizzle", "icon": "cloud-rain"},
    55: {"description": "Dense drizzle", "icon": "cloud-showers-heavy"},
    61: {"description": "Slight rain", "icon": "cloud-rain"},
    63: {"description": "Moderate rain", "icon": "cloud-showers-heavy"},
    65: {"description": "Heavy rain", "icon": "cloud-showers-water"},
    71: {"description": "Slight snow", "icon": "snowflake"},
    73: {"description": "Moderate snow", "icon": "snowflake"},
    75: {"description": "Heavy snow", "icon": "snowflake"},
    77: {"description": "Snow grains", "icon": "snowflake"},
    80: {"description": "Slight rain showers", "icon": "cloud-sun-rain"},
    81: {"description": "Moderate rain showers", "icon": "cloud-showers-heavy"},
    82: {"description": "Violent rain showers", "icon": "cloud-showers-water"},
    85: {"description": "Slight snow showers", "icon": "snowflake"},
    86: {"description": "Heavy snow showers", "icon": "snowflake"},
    95: {"description": "Thunderstorm", "icon": "cloud-bolt"},
    96: {"description": "Thunderstorm with slight hail", "icon": "cloud-meatball"},
    99: {"description": "Thunderstorm with heavy hail", "icon": "cloud-meatball"},
}

# Night variants of icons
NIGHT_ICON_MAPPING = {
    "cloud-sun": "cloud-moon",
    "cloud-sun-rain": "cloud-moon-rain",
    "sun": "moon",
}


class OpenMeteoProvider(WeatherProvider):
    """Open-Meteo API provider implementation.
    
    Supported temperature units:
    - CELSIUS: default, no conversion needed
    - FAHRENHEIT: uses temperature_unit=fahrenheit in API calls
    - KELVIN: converted from Celsius
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        
    def _get_temperature_unit_param(self) -> Optional[str]:
        """Get the temperature_unit parameter for API calls."""
        if self.unit == TemperatureUnit.FAHRENHEIT:
            return "fahrenheit"
        return None  # Celsius is default
        
    def _get_icon(self, code: int, is_day: bool = True) -> WeatherCondition:
        weather_info = WEATHER_CODES.get(
            code, {"description": "Unknown", "icon": "cloud"}
        )
        icon = weather_info["icon"]

        # Use night variant if available and it's night
        if not is_day and icon in NIGHT_ICON_MAPPING:
            icon = NIGHT_ICON_MAPPING[icon]

        return WeatherCondition(description=weather_info["description"], icon=icon)

    def _fetch_weather(self) -> WeatherData:
        """Fetch weather data from OpenMeteo API."""
        if not (self.lat and self.lon):
            raise ValueError("Coordinates must be provided")
            
        logger.debug(f"OpenMeteo: Fetching weather with unit={self.unit}")
        
        # Build API parameters
        params = {
            'latitude': self.lat,
            'longitude': self.lon,
            'current': [
                'temperature_2m',
                'relative_humidity_2m',
                'apparent_temperature',
                'is_day',
                'precipitation',
                'weather_code',
                'pressure_msl'
            ],
            'daily': [
                'weather_code',
                'temperature_2m_max',
                'temperature_2m_min',
                'sunrise',
                'sunset',
                'precipitation_sum',
                'precipitation_probability_max',
                'sunshine_duration'  # Make sure this is included
            ],
            'timezone': 'auto'
        }
        
        logger.debug(f"OpenMeteo: API parameters: {params}")
        
        response = requests.get(self.base_url, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Log raw sunshine duration data
        if 'daily' in data and 'sunshine_duration' in data['daily']:
            logger.info(f"Raw sunshine duration data: {data['daily']['sunshine_duration']}")
        else:
            logger.warning("No sunshine duration data in API response")
            
        # Process current weather
        temp = data['current']['temperature_2m']
        feels_like = data['current']['apparent_temperature']
        
        logger.debug(f"OpenMeteo: Raw temperature from API: {temp}°")
        
        # Convert temperatures if needed (OpenMeteo always returns Celsius)
        if self.unit == TemperatureUnit.FAHRENHEIT:
            temp = TemperatureUnit.celsius_to_fahrenheit(temp)
            feels_like = TemperatureUnit.celsius_to_fahrenheit(feels_like)
        elif self.unit == TemperatureUnit.KELVIN:
            temp = TemperatureUnit.celsius_to_kelvin(temp)
            feels_like = TemperatureUnit.celsius_to_kelvin(feels_like)
        
        current = CurrentWeather(
            temperature=temp,
            feels_like=feels_like,
            humidity=data['current']['relative_humidity_2m'],
            pressure=data['current']['pressure_msl'],
            precipitation=data['current']['precipitation'],
            condition=self._get_icon(
                data['current']['weather_code'],
                bool(data['current']['is_day'])
            ),
            time=datetime.fromisoformat(data['current']['time']),
            unit=self.unit
        )
        logger.debug(f"OpenMeteo: Created CurrentWeather with unit={current.unit}, temp={current.temperature}")
        
        # Process daily forecasts
        daily_forecasts = []
        for i in range(len(data['daily']['time'])):
            min_temp = data['daily']['temperature_2m_min'][i]
            max_temp = data['daily']['temperature_2m_max'][i]
            
            # Convert min/max temperatures if needed
            if self.unit == TemperatureUnit.FAHRENHEIT:
                min_temp = TemperatureUnit.celsius_to_fahrenheit(min_temp)
                max_temp = TemperatureUnit.celsius_to_fahrenheit(max_temp)
            elif self.unit == TemperatureUnit.KELVIN:
                min_temp = TemperatureUnit.celsius_to_kelvin(min_temp)
                max_temp = TemperatureUnit.celsius_to_kelvin(max_temp)
            
            # Log sunshine duration for debugging
            sunshine_seconds = data['daily']['sunshine_duration'][i]
            sunshine_hours = sunshine_seconds / 3600
            logger.info(f"Day {data['daily']['time'][i]}: sunshine duration = {sunshine_seconds} seconds ({sunshine_hours:.1f}h)")
            
            daily_forecasts.append(
                DailyForecast(
                    date=datetime.fromisoformat(data['daily']['time'][i]),
                    min_temp=min_temp,
                    max_temp=max_temp,
                    condition=self._get_icon(
                        data['daily']['weather_code'][i],
                        True  # Always use day icons for daily forecast
                    ),
                    precipitation_amount=data['daily']['precipitation_sum'][i],
                    precipitation_probability=data['daily']['precipitation_probability_max'][i],
                    sunshine_duration=timedelta(seconds=sunshine_seconds),
                    unit=self.unit
                )
            )
            
        # Create WeatherData object
        weather_data = WeatherData(
            current=current,
            daily_forecast=daily_forecasts,
            sunrise=datetime.fromisoformat(data['daily']['sunrise'][0]),
            sunset=datetime.fromisoformat(data['daily']['sunset'][0]),
            is_day=bool(data['current']['is_day']),
            attribution="Weather data provided by Open-Meteo.com"
        )
        
        # Log final weather data
        logger.info(f"Created WeatherData object with {len(weather_data.daily_forecast)} days of forecast")
        if weather_data.daily_forecast:
            logger.info(f"First day sunshine duration: {weather_data.daily_forecast[0].sunshine_duration}")
            
        return weather_data
