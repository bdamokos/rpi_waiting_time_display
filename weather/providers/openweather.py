import requests
from datetime import datetime, timedelta
from typing import Dict, Optional
import logging
import os
from .base import WeatherProvider
from ..models import WeatherData, CurrentWeather, WeatherCondition, DailyForecast, AirQuality, TemperatureUnit

logger = logging.getLogger(__name__)

# Weather code mapping to Font Awesome icons
WEATHER_CODES: Dict[str, Dict[str, str]] = {
    # Main weather conditions
    "Clear": {"description": "Clear sky", "icon": "sun"},
    "Clouds": {"description": "Cloudy", "icon": "cloud"},
    "Rain": {"description": "Rain", "icon": "cloud-rain"},
    "Drizzle": {"description": "Drizzle", "icon": "cloud-rain"},
    "Thunderstorm": {"description": "Thunderstorm", "icon": "cloud-bolt"},
    "Snow": {"description": "Snow", "icon": "snowflake"},
    "Mist": {"description": "Misty", "icon": "cloud"},
    "Smoke": {"description": "Smoky", "icon": "cloud"},
    "Haze": {"description": "Hazy", "icon": "cloud"},
    "Dust": {"description": "Dusty", "icon": "cloud"},
    "Fog": {"description": "Foggy", "icon": "cloud"},
    "Sand": {"description": "Sandy", "icon": "cloud"},
    "Ash": {"description": "Volcanic ash", "icon": "cloud"},
    "Squall": {"description": "Squall", "icon": "cloud-showers-heavy"},
    "Tornado": {"description": "Tornado", "icon": "tornado"},
}

# Night variants of icons
NIGHT_ICON_MAPPING = {
    "sun": "moon",
    "cloud-sun": "cloud-moon",
    "cloud-sun-rain": "cloud-moon-rain",
}

# Air Quality Index labels
AQI_LABELS = {
    1: "Good",
    2: "Fair",
    3: "Moderate",
    4: "Poor",
    5: "Very Poor"
}

class OpenWeatherProvider(WeatherProvider):
    """OpenWeatherMap API provider implementation.
    
    Supported temperature units:
    - CELSIUS: uses units=metric in API calls
    - FAHRENHEIT: uses units=imperial in API calls
    - KELVIN: uses units=standard in API calls (default)
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = os.getenv('OPENWEATHER_API_KEY')
        if not self.api_key:
            raise ValueError("OPENWEATHER_API_KEY environment variable is required")
        self.base_url = "https://api.openweathermap.org/data/2.5"
        
    def _get_units_param(self) -> Optional[str]:
        """Get the units parameter for API calls."""
        if self.unit == TemperatureUnit.CELSIUS:
            return "metric"
        elif self.unit == TemperatureUnit.FAHRENHEIT:
            return "imperial"
        return None  # Kelvin is default, no units parameter needed
        
    def _get_air_quality(self, params: dict) -> Optional[AirQuality]:
        """Get air quality data if coordinates are available."""
        try:
            response = requests.get(f"{self.base_url}/air_pollution", params=params)
            response.raise_for_status()
            data = response.json()
            
            aqi = data['list'][0]['main']['aqi']
            return AirQuality(
                aqi=aqi,
                label=AQI_LABELS.get(aqi, "Unknown"),
                components=data['list'][0]['components']
            )
        except Exception as e:
            logger.error(f"Error fetching air quality: {e}")
            return None
            
    def _fetch_weather(self) -> WeatherData:
        """Fetch weather data from OpenWeather API."""
        if not (self.lat and self.lon):
            raise ValueError("Coordinates must be provided")
            
        logger.debug(f"OpenWeather: Fetching weather with unit={self.unit}")
            
        # Get current weather
        params = {
            'appid': self.api_key,
            'lat': self.lat,
            'lon': self.lon,
        }
        
        # Add units if not using Kelvin
        units = self._get_units_param()
        if units:
            params['units'] = units
            
        response = requests.get(f"{self.base_url}/weather", params=params)
        response.raise_for_status()
        current_data = response.json()
        
        # Process current weather
        temp = current_data['main']['temp']
        feels_like = current_data['main']['feels_like']
        
        logger.debug(f"OpenWeather: Raw temperature from API: {temp}°")
        
        current = CurrentWeather(
            temperature=temp,
            feels_like=feels_like,
            humidity=current_data['main']['humidity'],
            pressure=current_data['main']['pressure'],
            precipitation=current_data.get('rain', {}).get('1h', 0.0) + current_data.get('snow', {}).get('1h', 0.0),  # Combine rain and snow
            condition=self._get_icon(
                current_data['weather'][0]['main'],
                self._is_daytime(current_data['dt'], current_data['sys']['sunrise'], current_data['sys']['sunset'])
            ),
            time=datetime.fromtimestamp(current_data['dt']),
            unit=self.unit
        )
        logger.debug(f"OpenWeather: Created CurrentWeather with unit={current.unit}, temp={current.temperature}")
        
        # Get forecast data with same parameters
        response = requests.get(f"{self.base_url}/forecast", params=params)
        response.raise_for_status()
        forecast_data = response.json()
        
        # Process daily forecasts (group by date)
        daily_forecasts = []
        by_date = {}
        
        for item in forecast_data['list']:
            date = datetime.fromtimestamp(item['dt']).date()
            if date not in by_date:
                by_date[date] = {
                    'temps': [],
                    'conditions': [],
                    'precipitation': 0.0
                }
            
            temp = item['main']['temp']
            by_date[date]['temps'].append(temp)
            by_date[date]['conditions'].append(item['weather'][0]['main'])
            by_date[date]['precipitation'] += item.get('rain', {}).get('3h', 0)
            
        for date, data in by_date.items():
            # Get most common condition for the day
            condition = max(set(data['conditions']), key=data['conditions'].count)
            
            # Get min/max temps
            min_temp = min(data['temps'])
            max_temp = max(data['temps'])
            
            daily_forecasts.append(
                DailyForecast(
                    date=datetime.combine(date, datetime.min.time()),
                    min_temp=min_temp,
                    max_temp=max_temp,
                    condition=self._get_icon(condition, True),  # Always use day icons for daily forecast
                    precipitation_amount=data['precipitation'],
                    unit=self.unit
                )
            )
            
        # Sort forecasts by date
        daily_forecasts.sort(key=lambda x: x.date)
        
        # Get air quality data
        air_quality = self._get_air_quality(params)
        
        return WeatherData(
            current=current,
            daily_forecast=daily_forecasts[:7],  # Limit to 7 days
            sunrise=datetime.fromtimestamp(current_data['sys']['sunrise']),
            sunset=datetime.fromtimestamp(current_data['sys']['sunset']),
            is_day=self._is_daytime(
                current_data['dt'],
                current_data['sys']['sunrise'],
                current_data['sys']['sunset']
            ),
            air_quality=air_quality,
            attribution="Weather data by OpenWeatherMap"
        ) 
        
    def _get_icon(self, condition: str, is_day: bool = True) -> WeatherCondition:
        """Convert OpenWeather condition to our standard format."""
        weather_info = WEATHER_CODES.get(condition, {"description": condition, "icon": "cloud"})
        icon = weather_info["icon"]
        
        # Use night variant if available and it's night
        if not is_day and icon in NIGHT_ICON_MAPPING:
            icon = NIGHT_ICON_MAPPING[icon]
            
        return WeatherCondition(
            description=weather_info["description"],
            icon=icon
        )
        
    def _is_daytime(self, current: int, sunrise: int, sunset: int) -> bool:
        """Check if the given timestamp is during daytime."""
        return sunrise <= current <= sunset 