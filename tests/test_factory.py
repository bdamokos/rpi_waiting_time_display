import pytest
import os
from weather.providers.factory import create_weather_provider
from weather.providers.openmeteo import OpenMeteoProvider
from weather.providers.openweather import OpenWeatherProvider
from weather.models import TemperatureUnit

def test_create_openmeteo_provider(monkeypatch):
    """Test creating OpenMeteo provider"""
    monkeypatch.setenv('Coordinates_LAT', '50.8505')
    monkeypatch.setenv('Coordinates_LNG', '4.3488')
    
    provider = create_weather_provider('openmeteo')
    assert isinstance(provider, OpenMeteoProvider)
    assert provider.lat == '50.8505'
    assert provider.lon == '4.3488'
    assert provider.unit == TemperatureUnit.CELSIUS

def test_create_openweather_provider(monkeypatch):
    """Test creating OpenWeather provider"""
    monkeypatch.setenv('Coordinates_LAT', '50.8505')
    monkeypatch.setenv('Coordinates_LNG', '4.3488')
    monkeypatch.setenv('OPENWEATHER_API_KEY', 'test_api_key')
    
    provider = create_weather_provider('openweather')
    assert isinstance(provider, OpenWeatherProvider)
    assert provider.lat == '50.8505'
    assert provider.lon == '4.3488'
    assert provider.unit == TemperatureUnit.CELSIUS

def test_create_provider_with_explicit_coordinates():
    """Test creating provider with explicit coordinates"""
    provider = create_weather_provider('openmeteo', lat='51.5074', lon='-0.1278')
    assert isinstance(provider, OpenMeteoProvider)
    assert provider.lat == '51.5074'
    assert provider.lon == '-0.1278'

def test_create_provider_with_unit():
    """Test creating provider with specific temperature unit"""
    provider = create_weather_provider('openmeteo', lat='51.5074', lon='-0.1278', unit='fahrenheit')
    assert provider.unit == TemperatureUnit.FAHRENHEIT

def test_missing_coordinates(monkeypatch):
    """Test error when coordinates are missing"""
    # Clear environment variables
    monkeypatch.delenv('Coordinates_LAT', raising=False)
    monkeypatch.delenv('Coordinates_LNG', raising=False)
    
    with pytest.raises(ValueError, match="Coordinates must be provided"):
        create_weather_provider('openmeteo')

def test_missing_api_key(monkeypatch):
    """Test fallback to OpenMeteo when OpenWeather API key is missing"""
    # Clear API key environment variable
    monkeypatch.delenv('OPENWEATHER_API_KEY', raising=False)
    
    provider = create_weather_provider('openweather', lat='51.5074', lon='-0.1278')
    assert isinstance(provider, OpenMeteoProvider)  # Should fallback to OpenMeteo
    assert provider.lat == '51.5074'
    assert provider.lon == '-0.1278'

def test_invalid_provider():
    """Test error with invalid provider name"""
    with pytest.raises(ValueError, match="Unknown provider"):
        create_weather_provider('invalid_provider', lat='51.5074', lon='-0.1278') 