import pytest
from pathlib import Path
import os
import shutil
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@pytest.fixture(scope="session", autouse=True)
def manage_env_files():
    """Backup real .env files and replace with test versions, restore after tests"""
    display_dir = Path.home() / 'display_programme'
    transit_dir = Path.home() / 'brussels_transit'
    env_files = [
        (display_dir / '.env', display_dir / '.env.test'),
        (transit_dir / '.env', transit_dir / '.env.test'),
        (transit_dir / 'app' / 'config' / 'local.py', transit_dir / 'app' / 'config' / 'local.py.test')
    ]

    # Backup existing files and replace with test versions
    backups = []
    for real_file, test_file in env_files:
        if real_file.exists():
            backup_file = real_file.with_suffix('.backup')
            shutil.copy2(real_file, backup_file)
            backups.append((real_file, backup_file))
            logger.debug(f"Backed up {real_file} to {backup_file}")

        if test_file.exists():
            shutil.copy2(test_file, real_file)
            logger.debug(f"Replaced {real_file} with test version from {test_file}")

    yield  # Run the tests

    # Restore original files
    for real_file, backup_file in backups:
        if backup_file.exists():
            shutil.copy2(backup_file, real_file)
            backup_file.unlink()
            logger.debug(f"Restored {real_file} from {backup_file}")

@pytest.fixture
def mock_env_vars():
    """Provide test environment variables"""
    return {
        'BUS_API_BASE_URL': 'http://127.0.0.1:5001/',
        'Provider': 'test_provider',
        'Stop_ID': '2100',  # This is our test stop ID
        'Lines': '0090',
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