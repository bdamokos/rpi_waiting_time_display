from typing import Optional
from .base import WeatherProvider
from .openmeteo import OpenMeteoProvider
from .openweather import OpenWeatherProvider
from ..models import TemperatureUnit
import os
import logging

logger = logging.getLogger(__name__)

def create_weather_provider(
    provider_name: str,
    lat: Optional[str] = None,
    lon: Optional[str] = None,
    unit: str = None
) -> WeatherProvider:
    """Create a weather provider instance based on the provider name.
    
    Args:
        provider_name: Name of the provider ("openmeteo" or "openweather")
        lat: Optional latitude
        lon: Optional longitude
        unit: Temperature unit ("celsius", "fahrenheit", or "kelvin")
        
    Returns:
        WeatherProvider instance
        
    Raises:
        ValueError: If provider_name is invalid or coordinates are missing
    """
    # Use environment variables if coordinates not provided - default to Brussels
    lat = lat or os.getenv('Coordinates_LAT', 50.8503)
    lon = lon or os.getenv('Coordinates_LNG', 4.3517)
    unit = unit or os.getenv('weather_unit', 'celsius').lower()
    
    # Convert unit string to enum
    try:
        unit_enum = TemperatureUnit(unit)
    except ValueError:
        logger.warning(f"Invalid temperature unit '{unit}', defaulting to Celsius")
        unit_enum = TemperatureUnit.CELSIUS
    
    # Check coordinates before creating any provider
    if not lat or not lon:
        raise ValueError("Coordinates must be provided either as arguments or environment variables")
    
    provider_name = provider_name.lower()
    if provider_name == "openmeteo":
        return OpenMeteoProvider(lat=lat, lon=lon, unit=unit_enum)
    elif provider_name == "openweather" or provider_name == "openweathermap":
        api_key = os.getenv('OPENWEATHER_API_KEY')
        if not api_key:
            logger.warning("OPENWEATHER_API_KEY environment variable is missing, falling back to OpenMeteo")
            return OpenMeteoProvider(lat=lat, lon=lon, unit=unit_enum)
        return OpenWeatherProvider(lat=lat, lon=lon, unit=unit_enum)
    else:
        raise ValueError(f"Unknown provider: {provider_name}") 