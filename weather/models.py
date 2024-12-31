from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta

class WeatherCondition(BaseModel):
    description: str
    icon: str  # Font Awesome icon name without .svg extension

class CurrentWeather(BaseModel):
    temperature: float
    feels_like: float
    humidity: int
    pressure: float
    condition: WeatherCondition
    time: datetime = Field(default_factory=datetime.now)

class AirQuality(BaseModel):
    aqi: int
    label: str
    components: Optional[dict] = None

class DailyForecast(BaseModel):
    """Daily weather forecast data including sunshine duration.
    
    Note on sunshine duration:
    Following the WMO (World Meteorological Organization) definition, sunshine duration
    is calculated as the time during which direct solar irradiance exceeds 120 W/m².
    This will always be less than the total daylight duration due to:
    - Dawn and dusk periods
    - Cloud cover
    - Atmospheric conditions
    A value of 0 indicates no direct sunlight exceeded this threshold during the day.
    """
    date: datetime
    min_temp: float
    max_temp: float
    condition: WeatherCondition
    precipitation_probability: Optional[float] = None
    precipitation_amount: Optional[float] = None
    sunshine_duration: Optional[timedelta] = None

class WeatherData(BaseModel):
    current: CurrentWeather
    air_quality: Optional[AirQuality] = None
    daily_forecast: List[DailyForecast] = []
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None
    is_day: bool = True
    attribution: Optional[str] = None  # Required for some providers like Open-Meteo 