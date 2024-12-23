import os
import pytest
from dotenv import load_dotenv

@pytest.fixture(autouse=True)
def load_env():
    """Load environment variables from .env file for all tests"""
    pass

@pytest.fixture
def mock_env_vars(monkeypatch):
    """Fixture to set mock environment variables"""
    # Clear existing environment variables
    for key in os.environ.keys():
        monkeypatch.delenv(key, raising=False)

    test_env = {
        'OPENWEATHER_API_KEY': 'test_weather_key',
        'TRANSPORT_API_KEY': 'test_transport_key',
        'TRANSPORT_APP_ID': 'test_app_id',
        'AVIATION_API_KEY': 'test_aviation_key',
        'Coordinates_LAT': '51.5085',
        'Coordinates_LNG': '-0.1257',
        'City': 'Test City',
        'Country': 'Test Country',
        'BUS_API_BASE_URL': 'http://127.0.0.1:5001/',
        'Provider': 'test_provider',
        'Lines': '64,59',
        'Stops': '2100',
        'mock_display_type': 'bw',
        'display_model': 'epd2in13'
    }
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
    return test_env

@pytest.fixture
def sample_weather_response():
    """Fixture providing a sample weather API response"""
    return {
        "coord": {"lon": -0.1257, "lat": 51.5085},
        "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
        "main": {
            "temp": 15.5,
            "feels_like": 14.8,
            "temp_min": 14.0,
            "temp_max": 16.7,
            "pressure": 1015,
            "humidity": 76
        },
        "wind": {"speed": 3.6, "deg": 250},
        "clouds": {"all": 0},
        "dt": 1640995200,
        "sys": {
            "sunrise": 1640937600,
            "sunset": 1640968800
        }
    }

@pytest.fixture
def sample_bus_response():
    """Fixture providing a sample bus API response"""
    return {
        "name": "Test Stop",
        "lines": {
            "64": {
                "Test Destination": [
                    {
                        "minutes": 5,
                        "message": None
                    }
                ]
            }
        }
    } 