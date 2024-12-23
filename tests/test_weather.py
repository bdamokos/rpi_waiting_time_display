import pytest
import responses
import os
from weather import WeatherService
from unittest.mock import patch, MagicMock

@pytest.fixture
def weather_service(mock_env_vars):
    """Fixture providing a WeatherService instance with mocked environment variables"""
    with patch.dict(os.environ, mock_env_vars, clear=True):
        return WeatherService()

@pytest.fixture
def mock_responses():
    """Fixture to mock API responses using the responses library"""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps

def test_weather_service_initialization(weather_service, mock_env_vars):
    """Test WeatherService initialization with environment variables"""
    assert weather_service.api_key == mock_env_vars['OPENWEATHER_API_KEY']
    assert float(weather_service.lat) == float(mock_env_vars['Coordinates_LAT'])
    assert float(weather_service.lon) == float(mock_env_vars['Coordinates_LNG'])
    assert weather_service.city == mock_env_vars['City']
    assert weather_service.country == mock_env_vars['Country']

@responses.activate
def test_get_weather_success(weather_service, mock_responses, sample_weather_response, mock_env_vars):
    """Test successful weather data retrieval"""
    # Mock the API response with the correct URL pattern
    mock_responses.add(
        responses.GET,
        weather_service.base_url,
        match=[
            responses.matchers.query_param_matcher({
                'lat': str(float(weather_service.lat)),
                'lon': str(float(weather_service.lon)),
                'appid': mock_env_vars['OPENWEATHER_API_KEY'],
                'units': 'metric'
            })
        ],
        json=sample_weather_response,
        status=200
    )

    weather_data = weather_service.get_weather()
    
    assert weather_data is not None
    assert weather_data['temperature'] == round(sample_weather_response['main']['temp'])
    assert weather_data['description'] == sample_weather_response['weather'][0]['main']
    assert weather_data['humidity'] == sample_weather_response['main']['humidity']
    assert 'time' in weather_data
    assert weather_data['icon'] == sample_weather_response['weather'][0]['icon']
    assert weather_data['feels_like'] == round(sample_weather_response['main']['feels_like'])
    assert weather_data['pressure'] == sample_weather_response['main']['pressure']

@responses.activate
def test_get_weather_api_error(weather_service, mock_responses, mock_env_vars):
    """Test weather data retrieval with API error"""
    # Mock a failed API response with the correct URL pattern
    mock_responses.add(
        responses.GET,
        weather_service.base_url,
        match=[
            responses.matchers.query_param_matcher({
                'lat': str(float(weather_service.lat)),
                'lon': str(float(weather_service.lon)),
                'appid': mock_env_vars['OPENWEATHER_API_KEY'],
                'units': 'metric'
            })
        ],
        json={"message": "API error"},
        status=401
    )

    weather_data = weather_service.get_weather()
    
    assert weather_data is not None
    assert weather_data['temperature'] == '--'
    assert weather_data['description'] == 'Error'
    assert weather_data['humidity'] == '--'
    assert 'time' in weather_data
    assert weather_data['icon'] == 'unknown'

@pytest.mark.parametrize("aqi_value,expected_label", [
    (1, "Good"),
    (2, "Fair"),
    (3, "Moderate"),
    (4, "Poor"),
    (5, "Very Poor")
])
def test_air_quality_labels(weather_service, aqi_value, expected_label):
    """Test air quality index labels"""
    assert weather_service.aqi_labels[aqi_value] == expected_label

@responses.activate
def test_get_air_quality_success(weather_service, mock_responses, mock_env_vars):
    """Test successful air quality data retrieval"""
    mock_air_quality_response = {
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

    mock_responses.add(
        responses.GET,
        weather_service.air_pollution_url,
        match=[
            responses.matchers.query_param_matcher({
                'lat': str(float(weather_service.lat)),
                'lon': str(float(weather_service.lon)),
                'appid': mock_env_vars['OPENWEATHER_API_KEY']
            })
        ],
        json=mock_air_quality_response,
        status=200
    )

    air_quality = weather_service.get_air_quality()
    
    assert air_quality is not None
    assert air_quality['aqi'] == 1
    assert air_quality['aqi_label'] == "Good"
    assert 'components' in air_quality