import pytest
from pathlib import Path
import os
import tempfile

# Keep imports such as log_config and dotenv away from a developer's real home.
TEST_HOME = Path(tempfile.mkdtemp(prefix="rpi-waiting-time-display-tests-"))
os.environ["HOME"] = str(TEST_HOME)

@pytest.fixture
def mock_env_vars():
    """Provide test environment variables"""
    return {
        'BUS_API_BASE_URL': 'http://127.0.0.1:5001/',
        'Provider': 'test_provider',
        'Stops': '2100',
        'Lines': '64',
        'City': 'Test City',
        'Country': 'Test Country',
        'Coordinates_LAT': '51.5085',
        'Coordinates_LNG': '-0.1257',
        'OPENWEATHER_API_KEY': 'test_weather_key',
        'AVIATION_API_KEY': 'test_aviation_key'
    }

@pytest.fixture
def sample_bus_response():
    """Provide sample bus service response data"""
    return {
        'lines': {
            '64': {
                'Test Destination': [
                    {'message': None, 'minutes': 5}
                ]
            }
        },
        'name': 'Test Stop'
    }
