from abc import ABC, abstractmethod
from ..models import WeatherData
from typing import Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class WeatherProvider(ABC):
    def __init__(self, lat: Optional[float] = None, lon: Optional[float] = None, 
                 city: Optional[str] = None, country: Optional[str] = None):
        self.lat = lat
        self.lon = lon
        self.city = city
        self.country = country
        self._cache = None
        self._last_update = None
        self.update_interval = timedelta(minutes=10)  # Default 10 minutes
        
    @property
    def cache_valid(self) -> bool:
        """Check if cached data is still valid"""
        if not self._cache or not self._last_update:
            return False
        return datetime.now() - self._last_update < self.update_interval
    
    def get_weather(self) -> WeatherData:
        """Get weather data, using cache if valid"""
        if self.cache_valid:
            return self._cache
            
        try:
            weather_data = self._fetch_weather()
            self._cache = weather_data
            self._last_update = datetime.now()
            return weather_data
        except Exception as e:
            logger.error(f"Error fetching weather data: {e}")
            if self._cache:  # Return stale cache if available
                logger.warning("Returning stale cached data")
                return self._cache
            raise
    
    @abstractmethod
    def _fetch_weather(self) -> WeatherData:
        """Fetch fresh weather data from the provider"""
        pass 