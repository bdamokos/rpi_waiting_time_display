from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
from enum import Enum

class TemperatureUnit(str, Enum):
    """Temperature unit configuration.
    
    Supported units:
    - CELSIUS: °C (default)
    - FAHRENHEIT: °F
    - KELVIN: K
    """
    CELSIUS = "celsius"
    FAHRENHEIT = "fahrenheit"
    KELVIN = "kelvin"
    
    @staticmethod
    def celsius_to_kelvin(celsius: float) -> float:
        """Convert Celsius to Kelvin."""
        return celsius + 273.15
        
    @staticmethod
    def kelvin_to_celsius(kelvin: float) -> float:
        """Convert Kelvin to Celsius."""
        return kelvin - 273.15
        
    @staticmethod
    def celsius_to_fahrenheit(celsius: float) -> float:
        """Convert Celsius to Fahrenheit."""
        return (celsius * 9/5) + 32
        
    @staticmethod
    def fahrenheit_to_celsius(fahrenheit: float) -> float:
        """Convert Fahrenheit to Celsius."""
        return (fahrenheit - 32) * 5/9
        
    @staticmethod
    def kelvin_to_fahrenheit(kelvin: float) -> float:
        """Convert Kelvin to Fahrenheit."""
        celsius = TemperatureUnit.kelvin_to_celsius(kelvin)
        return TemperatureUnit.celsius_to_fahrenheit(celsius)
        
    @staticmethod
    def fahrenheit_to_kelvin(fahrenheit: float) -> float:
        """Convert Fahrenheit to Kelvin."""
        celsius = TemperatureUnit.fahrenheit_to_celsius(fahrenheit)
        return TemperatureUnit.celsius_to_kelvin(celsius)
        
    def convert_from(self, value: float, from_unit: "TemperatureUnit") -> float:
        """Convert a temperature value from another unit to this unit.
        
        Args:
            value: The temperature value to convert
            from_unit: The unit to convert from
            
        Returns:
            The converted temperature value
        """
        if self == from_unit:
            return value
            
        # Convert to Celsius first if needed
        if from_unit == TemperatureUnit.FAHRENHEIT:
            value = TemperatureUnit.fahrenheit_to_celsius(value)
        elif from_unit == TemperatureUnit.KELVIN:
            value = TemperatureUnit.kelvin_to_celsius(value)
            
        # Then convert from Celsius to target unit
        if self == TemperatureUnit.FAHRENHEIT:
            return TemperatureUnit.celsius_to_fahrenheit(value)
        elif self == TemperatureUnit.KELVIN:
            return TemperatureUnit.celsius_to_kelvin(value)
        else:  # CELSIUS
            return value

class WeatherCondition(BaseModel):
    description: str
    icon: str  # Font Awesome icon name without .svg extension

class CurrentWeather(BaseModel):
    temperature: float
    feels_like: float
    humidity: int
    pressure: float
    condition: WeatherCondition
    precipitation: float = 0.0  # Current precipitation in mm
    time: datetime = Field(default_factory=datetime.now)
    unit: TemperatureUnit = TemperatureUnit.CELSIUS  # Default to Celsius

class AirQuality(BaseModel):
    aqi: int
    label: str
    components: Optional[dict] = None

class DailyForecast(BaseModel):
    """Daily weather forecast data.
    
    Attributes:
        date: The date of the forecast
        min_temp: Minimum temperature in the specified unit
        max_temp: Maximum temperature in the specified unit
        condition: Weather condition
        precipitation_probability: Probability of precipitation (0-100)
        precipitation_amount: Amount of precipitation in mm
        sunshine_duration: Duration of sunshine in seconds.
            According to WMO definition (WMO, 2003), sunshine duration is defined as the period
            during which direct solar irradiance exceeds a threshold value of 120 W/m².
            The sunshine duration is the length of time that the ground surface is irradiated by
            direct solar radiation (i.e., sunlight reaching the earth's surface directly from the sun).
        unit: Temperature unit (Celsius, Fahrenheit, or Kelvin)
    """
    date: datetime
    min_temp: float
    max_temp: float
    condition: WeatherCondition
    precipitation_amount: float = 0.0
    precipitation_probability: float = 0.0
    sunshine_duration: timedelta = timedelta()
    unit: TemperatureUnit = TemperatureUnit.CELSIUS

class WeatherData(BaseModel):
    current: CurrentWeather
    air_quality: Optional[AirQuality] = None
    daily_forecast: List[DailyForecast] = []
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None
    is_day: bool = True
    attribution: Optional[str] = None  # Required for some providers like Open-Meteo 