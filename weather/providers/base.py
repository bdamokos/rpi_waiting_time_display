from abc import ABC, abstractmethod
from ..models import WeatherData, TemperatureUnit
from typing import Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class WeatherProvider(ABC):
    """Base class for weather data providers."""
    
    def __init__(
        self,
        lat: Optional[float] = None,
        lon: Optional[float] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        cache_duration: timedelta = timedelta(minutes=10),
        unit: TemperatureUnit = TemperatureUnit.CELSIUS
    ):
        """Initialize weather provider.
        
        Args:
            lat: Latitude
            lon: Longitude
            city: City name
            country: Country code
            cache_duration: How long to cache weather data
            unit: Temperature unit (celsius, fahrenheit, or kelvin)
        """
        self.lat = lat
        self.lon = lon
        self.city = city
        self.country = country
        self.cache_duration = cache_duration
        self._unit = unit
        self._cache = None
        self._last_update = None
        
    @property
    def unit(self) -> TemperatureUnit:
        """Get the current temperature unit."""
        return self._unit
        
    @unit.setter
    def unit(self, value: TemperatureUnit):
        """Set the temperature unit and clear the cache."""
        self._unit = value
        self._cache = None  # Clear cache when unit changes
        
    def get_weather(self) -> WeatherData:
        """Get weather data, using cache if available."""
        now = datetime.now()
        
        # Return cached data if available and not expired
        if (
            self._cache is not None
            and self._last_update is not None
            and now - self._last_update < self.cache_duration
        ):
            return self._cache
            
        try:
            # Fetch fresh data
            weather_data = self._fetch_weather()
            self._cache = weather_data
            self._last_update = now
            return weather_data
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            raise
            
    @abstractmethod
    def _fetch_weather(self) -> WeatherData:
        """Fetch weather data from provider API.
        
        This method should be implemented by each provider to fetch and process
        weather data according to the provider's specific API.
        
        Returns:
            WeatherData object containing current conditions and forecast
        """
        pass 