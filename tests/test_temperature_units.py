import pytest
from unittest.mock import patch, MagicMock
from weather.providers.factory import create_weather_provider
from weather.models import TemperatureUnit

def test_weather_unit_from_env():
    """Test that the weather provider respects the temperature unit from environment variables."""
    
    test_temp_celsius = 25.0
    
    # Mock the API response with a temperature in Celsius
    mock_response = MagicMock()
    mock_response.json.return_value = {
        'current': {
            'temperature_2m': test_temp_celsius,
            'relative_humidity_2m': 50,
            'apparent_temperature': test_temp_celsius,
            'is_day': 1,
            'precipitation': 0,
            'weather_code': 0,
            'pressure_msl': 1013.0,
            'time': '2024-01-01T12:00:00'
        },
        'daily': {
            'time': ['2024-01-01'],
            'temperature_2m_min': [20.0],
            'temperature_2m_max': [30.0],
            'weather_code': [0],
            'sunrise': ['2024-01-01T08:00:00'],
            'sunset': ['2024-01-01T16:00:00'],
            'precipitation_sum': [0],
            'precipitation_probability_max': [0],
            'sunshine_duration': [3600]
        }
    }
    
    test_cases = [
        ('celsius', test_temp_celsius),  # Should remain unchanged
        ('fahrenheit', (test_temp_celsius * 9/5) + 32),  # Convert to Fahrenheit
        ('kelvin', test_temp_celsius + 273.15)  # Convert to Kelvin
    ]
    
    with patch('weather.providers.openmeteo.requests.get') as mock_get:
        mock_get.return_value = mock_response
        
        for unit_str, expected_temp in test_cases:
            with patch.dict('os.environ', {
                'weather_unit': unit_str,
                'Coordinates_LAT': '50.8503',
                'Coordinates_LNG': '4.3517'
            }, clear=True):
                provider = create_weather_provider('openmeteo')
                weather_data = provider.get_weather()
                
                assert abs(weather_data.current.temperature - expected_temp) < 0.01, \
                    f"Expected {expected_temp} {unit_str}, got {weather_data.current.temperature}" 