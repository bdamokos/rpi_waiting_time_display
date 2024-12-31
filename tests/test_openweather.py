import pytest
from datetime import datetime
import responses
import os
from weather.providers.openweather import OpenWeatherProvider, WEATHER_CODES
from weather.models import TemperatureUnit

@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables."""
    monkeypatch.setenv('OPENWEATHER_API_KEY', 'test_api_key')
    monkeypatch.setenv('Coordinates_LAT', '50.8505')
    monkeypatch.setenv('Coordinates_LNG', '4.3488')

@pytest.fixture
def provider(mock_env):
    return OpenWeatherProvider(lat=50.8505, lon=4.3488)

@pytest.fixture
def sample_weather_response():
    return {
        "coord": {"lon": 4.3488, "lat": 50.8505},
        "weather": [{"id": 800, "main": "Clear", "description": "clear sky"}],
        "main": {
            "temp": 15.3,
            "feels_like": 14.8,
            "temp_min": 14.2,
            "temp_max": 16.1,
            "pressure": 1015,
            "humidity": 65
        },
        "dt": 1704106200,  # 2024-01-01 12:30:00 (middle of the day)
        "sys": {
            "sunrise": 1704096300,  # 2024-01-01 08:45:00
            "sunset": 1704126300    # 2024-01-01 16:45:00
        }
    }

@pytest.fixture
def sample_forecast_response():
    return {
        "list": [
            {
                "dt": 1704067200,  # 2024-01-01 12:00
                "main": {
                    "temp": 15.3,
                    "feels_like": 14.8,
                    "temp_min": 14.2,
                    "temp_max": 16.1,
                    "pressure": 1015,
                    "humidity": 65
                },
                "weather": [{"main": "Clear"}],
                "rain": {"3h": 0.0}
            },
            {
                "dt": 1704153600,  # 2024-01-02 12:00
                "main": {
                    "temp": 14.8,
                    "feels_like": 14.2,
                    "temp_min": 13.9,
                    "temp_max": 15.8,
                    "pressure": 1012,
                    "humidity": 70
                },
                "weather": [{"main": "Rain"}],
                "rain": {"3h": 2.1}
            }
        ]
    }

@pytest.fixture
def sample_air_quality_response():
    return {
        "list": [{
            "main": {"aqi": 1},
            "components": {
                "co": 200.34,
                "no2": 2.95,
                "o3": 60.84,
                "pm2_5": 4.11,
                "pm10": 7.32
            }
        }]
    }

@responses.activate
def test_fetch_weather(provider, sample_weather_response, sample_forecast_response, sample_air_quality_response):
    """Test successful weather data retrieval"""
    # Mock the API responses
    base_url = "https://api.openweathermap.org/data/2.5"
    
    responses.add(
        responses.GET,
        f"{base_url}/weather",
        json=sample_weather_response,
        status=200
    )
    
    responses.add(
        responses.GET,
        f"{base_url}/forecast",
        json=sample_forecast_response,
        status=200
    )
    
    responses.add(
        responses.GET,
        f"{base_url}/air_pollution",
        json=sample_air_quality_response,
        status=200
    )
    
    # Get weather data
    weather_data = provider.get_weather()
    
    # Test current weather
    assert weather_data.current.temperature == 15
    assert weather_data.current.feels_like == 15
    assert weather_data.current.humidity == 65
    assert weather_data.current.pressure == 1015
    assert weather_data.current.condition.description == "Clear sky"
    assert weather_data.current.condition.icon == "sun"
    
    # Test forecast
    assert len(weather_data.daily_forecast) > 0
    first_day = weather_data.daily_forecast[0]
    assert first_day.condition.description == "Clear sky"
    assert first_day.precipitation_amount == 0.0
    
    # Test air quality
    assert weather_data.air_quality is not None
    assert weather_data.air_quality.aqi == 1
    assert weather_data.air_quality.label == "Good"
    
    # Test sun times
    assert weather_data.sunrise == datetime.fromtimestamp(1704096300)  # 08:45
    assert weather_data.sunset == datetime.fromtimestamp(1704126300)   # 16:45
    assert weather_data.is_day  # Current time (12:30) is during the day
    
    # Test attribution
    assert weather_data.attribution == "Weather data by OpenWeatherMap"

@responses.activate
def test_error_handling(provider):
    """Test error handling and caching"""
    base_url = "http://api.openweathermap.org/data/2.5"
    
    # Mock a failed API response
    responses.add(
        responses.GET,
        f"{base_url}/weather",
        json={"error": "API error"},
        status=500
    )
    
    # First call should raise an exception
    with pytest.raises(Exception):
        provider.get_weather()
    
    # Cache should be empty
    assert provider._cache is None

def test_icon_mapping():
    """Test weather condition to icon mapping"""
    provider = OpenWeatherProvider(lat=50.8505, lon=4.3488)
    
    # Test day icons
    assert provider._get_icon("Clear", True).icon == "sun"
    assert provider._get_icon("Clouds", True).icon == "cloud"
    assert provider._get_icon("Rain", True).icon == "cloud-rain"
    
    # Test night variants
    assert provider._get_icon("Clear", False).icon == "moon"
    
    # Test unknown condition
    assert provider._get_icon("Unknown", True).icon == "cloud" 

@responses.activate
def test_temperature_units(provider, sample_weather_response, sample_forecast_response, sample_air_quality_response):
    """Test temperature unit handling"""
    base_url = "https://api.openweathermap.org/data/2.5"
    
    # Common parameters for all requests
    base_params = {
        'appid': 'test_api_key',
        'lat': '50.8505',
        'lon': '4.3488'
    }
    
    # Test Celsius (metric)
    provider.unit = TemperatureUnit.CELSIUS
    metric_params = base_params.copy()
    metric_params['units'] = 'metric'
    
    responses.add(
        responses.GET,
        f"{base_url}/weather",
        match=[responses.matchers.query_param_matcher(metric_params)],
        json=sample_weather_response,
        status=200
    )
    responses.add(
        responses.GET,
        f"{base_url}/forecast",
        match=[responses.matchers.query_param_matcher(metric_params)],
        json=sample_forecast_response,
        status=200
    )
    responses.add(
        responses.GET,
        f"{base_url}/air_pollution",
        match=[responses.matchers.query_param_matcher(base_params)],  # Air pollution doesn't use units
        json=sample_air_quality_response,
        status=200
    )
    weather_data = provider.get_weather()
    assert weather_data.current.unit == TemperatureUnit.CELSIUS
    
    # Test Fahrenheit (imperial)
    provider.unit = TemperatureUnit.FAHRENHEIT
    imperial_params = base_params.copy()
    imperial_params['units'] = 'imperial'
    
    responses.add(
        responses.GET,
        f"{base_url}/weather",
        match=[responses.matchers.query_param_matcher(imperial_params)],
        json=sample_weather_response,
        status=200
    )
    responses.add(
        responses.GET,
        f"{base_url}/forecast",
        match=[responses.matchers.query_param_matcher(imperial_params)],
        json=sample_forecast_response,
        status=200
    )
    responses.add(
        responses.GET,
        f"{base_url}/air_pollution",
        match=[responses.matchers.query_param_matcher(base_params)],  # Air pollution doesn't use units
        json=sample_air_quality_response,
        status=200
    )
    weather_data = provider.get_weather()
    assert weather_data.current.unit == TemperatureUnit.FAHRENHEIT
    
    # Test Kelvin (default)
    provider.unit = TemperatureUnit.KELVIN
    responses.add(
        responses.GET,
        f"{base_url}/weather",
        match=[responses.matchers.query_param_matcher(base_params)],  # No units param for Kelvin
        json=sample_weather_response,
        status=200
    )
    responses.add(
        responses.GET,
        f"{base_url}/forecast",
        match=[responses.matchers.query_param_matcher(base_params)],  # No units param for Kelvin
        json=sample_forecast_response,
        status=200
    )
    responses.add(
        responses.GET,
        f"{base_url}/air_pollution",
        match=[responses.matchers.query_param_matcher(base_params)],  # Air pollution doesn't use units
        json=sample_air_quality_response,
        status=200
    )
    weather_data = provider.get_weather()
    assert weather_data.current.unit == TemperatureUnit.KELVIN 