import pytest
from datetime import datetime, timedelta
import responses
from weather.providers.openmeteo import OpenMeteoProvider, WEATHER_CODES
from weather.models import TemperatureUnit

@pytest.fixture
def provider():
    return OpenMeteoProvider(lat=50.8505, lon=4.3488)  # Brussels coordinates

@pytest.fixture
def sample_response():
    return {
        "latitude": 50.875,
        "longitude": 4.375,
        "generationtime_ms": 0.2510547637939453,
        "utc_offset_seconds": 3600,
        "timezone": "Europe/Brussels",
        "timezone_abbreviation": "CET",
        "elevation": 28.0,
        "current_units": {
            "time": "iso8601",
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "apparent_temperature": "°C",
            "precipitation": "mm",
            "weather_code": "wmo code",
            "pressure_msl": "hPa",
            "is_day": ""
        },
        "current": {
            "time": "2024-01-01T12:00",
            "temperature_2m": 15.3,
            "relative_humidity_2m": 65,
            "apparent_temperature": 14.8,
            "precipitation": 0.0,
            "weather_code": 1,  # Mainly clear
            "pressure_msl": 1015.0,
            "is_day": 1
        },
        "daily_units": {
            "time": "iso8601",
            "weather_code": "wmo code",
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "sunrise": "iso8601",
            "sunset": "iso8601",
            "precipitation_sum": "mm",
            "precipitation_probability_max": "%",
            "sunshine_duration": "s"
        },
        "daily": {
            "time": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "weather_code": [1, 3, 61],  # Clear, Overcast, Light rain
            "temperature_2m_max": [16.2, 15.8, 14.5],
            "temperature_2m_min": [8.1, 7.9, 9.2],
            "sunrise": ["2024-01-01T08:45", "2024-01-02T08:45", "2024-01-03T08:45"],
            "sunset": ["2024-01-01T16:45", "2024-01-02T16:46", "2024-01-03T16:47"],
            "precipitation_sum": [0.0, 0.2, 5.6],
            "precipitation_probability_max": [0, 20, 80],
            "sunshine_duration": [28800, 14400, 7200]  # 8h, 4h, 2h in seconds
        }
    }

@responses.activate
def test_fetch_weather(provider, sample_response):
    """Test successful weather data retrieval"""
    # Mock the API response
    responses.add(
        responses.GET,
        provider.base_url,
        json=sample_response,
        status=200
    )
    
    # Get weather data
    weather_data = provider.get_weather()
    
    # Test current weather
    assert weather_data.current.temperature == 15
    assert weather_data.current.feels_like == 15
    assert weather_data.current.humidity == 65
    assert weather_data.current.pressure == 1015.0
    assert weather_data.current.condition.description == "Mainly clear"
    assert weather_data.current.condition.icon == "cloud-sun"
    
    # Test forecast
    assert len(weather_data.daily_forecast) == 3
    first_day = weather_data.daily_forecast[0]
    assert first_day.min_temp == 8
    assert first_day.max_temp == 16
    assert first_day.condition.description == "Mainly clear"
    assert first_day.precipitation_amount == 0.0
    assert first_day.precipitation_probability == 0
    assert first_day.sunshine_duration == timedelta(hours=8)
    
    # Test sun times
    assert weather_data.sunrise == datetime.fromisoformat("2024-01-01T08:45")
    assert weather_data.sunset == datetime.fromisoformat("2024-01-01T16:45")
    assert weather_data.is_day == True
    
    # Test attribution
    assert weather_data.attribution == "Weather data by Open-Meteo"

@responses.activate
def test_error_handling(provider):
    """Test error handling and caching"""
    # Mock a failed API response
    responses.add(
        responses.GET,
        provider.base_url,
        json={"error": "API error"},
        status=500
    )
    
    # First call should raise an exception
    with pytest.raises(Exception):
        provider.get_weather()
    
    # Cache should be empty
    assert provider._cache is None

def test_icon_mapping():
    """Test weather code to icon mapping"""
    provider = OpenMeteoProvider()
    
    # Test day icons
    assert provider._get_icon(0, True).icon == "sun"  # Clear sky
    assert provider._get_icon(3, True).icon == "cloud"  # Overcast
    assert provider._get_icon(95, True).icon == "cloud-bolt"  # Thunderstorm
    
    # Test night variants
    assert provider._get_icon(0, False).icon == "moon"  # Clear sky at night
    assert provider._get_icon(1, False).icon == "cloud-moon"  # Mainly clear at night
    
    # Test unknown code
    assert provider._get_icon(999, True).icon == "cloud"  # Unknown code 

@responses.activate
def test_temperature_units(provider, sample_response):
    """Test temperature unit handling"""
    base_url = "https://api.open-meteo.com/v1/forecast"
    
    # Common parameters for all requests
    base_params = {
        'latitude': '50.8505',
        'longitude': '4.3488',
        'current': [
            'temperature_2m',
            'relative_humidity_2m',
            'apparent_temperature',
            'precipitation',
            'weather_code',
            'pressure_msl',
            'is_day'
        ],
        'daily': [
            'weather_code',
            'temperature_2m_max',
            'temperature_2m_min',
            'sunrise',
            'sunset',
            'precipitation_sum',
            'precipitation_probability_max',
            'sunshine_duration'
        ],
        'timezone': 'auto'
    }
    
    # Test Celsius (default)
    provider.unit = TemperatureUnit.CELSIUS
    responses.add(
        responses.GET,
        base_url,
        match=[responses.matchers.query_param_matcher(base_params)],
        json=sample_response,
        status=200
    )
    weather_data = provider.get_weather()
    assert weather_data.current.unit == TemperatureUnit.CELSIUS
    
    # Test Fahrenheit
    provider.unit = TemperatureUnit.FAHRENHEIT
    fahrenheit_params = base_params.copy()
    fahrenheit_params['temperature_unit'] = 'fahrenheit'
    responses.add(
        responses.GET,
        base_url,
        match=[responses.matchers.query_param_matcher(fahrenheit_params)],
        json=sample_response,
        status=200
    )
    weather_data = provider.get_weather()
    assert weather_data.current.unit == TemperatureUnit.FAHRENHEIT
    
    # Test Kelvin (should fall back to Celsius)
    provider.unit = TemperatureUnit.KELVIN
    responses.add(
        responses.GET,
        base_url,
        match=[responses.matchers.query_param_matcher(base_params)],
        json=sample_response,
        status=200
    )
    weather_data = provider.get_weather()
    assert weather_data.current.unit == TemperatureUnit.KELVIN  # We now handle Kelvin conversion in the model 