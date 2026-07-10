from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from weather import WeatherService
from weather.models import (
    AirQuality,
    CurrentWeather,
    DailyForecast,
    TemperatureUnit,
    WeatherCondition,
    WeatherData,
)


@pytest.fixture
def weather_data():
    condition = WeatherCondition(description="Clear sky", icon="sun")
    return WeatherData(
        current=CurrentWeather(
            temperature=15.3,
            feels_like=14.8,
            humidity=65,
            pressure=1015,
            condition=condition,
            unit=TemperatureUnit.CELSIUS,
        ),
        air_quality=AirQuality(
            aqi=1,
            label="Good",
            components={"pm2_5": 4.11},
        ),
        daily_forecast=[
            DailyForecast(
                date=datetime(2024, 1, 2),
                min_temp=8,
                max_temp=16,
                condition=condition,
            )
        ],
        sunrise=datetime(2024, 1, 1, 8, 45),
        sunset=datetime(2024, 1, 1, 16, 45),
        is_day=True,
    )


@pytest.fixture
def weather_service(monkeypatch):
    monkeypatch.setenv("WEATHER_PROVIDER", "openweather")
    provider = MagicMock()
    with patch(
        "weather.display.create_weather_provider", return_value=provider
    ) as factory:
        service = WeatherService()
    return service, provider, factory


def test_weather_service_initialization(weather_service):
    service, provider, factory = weather_service

    assert service.provider is provider
    factory.assert_called_once_with("openweather")


def test_get_weather_success(weather_service, weather_data):
    service, provider, _factory = weather_service
    provider.get_weather.return_value = weather_data

    result = service.get_weather()

    assert result["temperature"] == 15.3
    assert result["description"] == "Clear sky"
    assert result["humidity"] == 65
    assert result["icon"] == "sun"
    assert result["feels_like"] == 14.8
    assert result["pressure"] == 1015
    assert result["daily_forecast"] == weather_data.daily_forecast


def test_get_weather_api_error(weather_service):
    service, provider, _factory = weather_service
    provider.get_weather.side_effect = RuntimeError("API error")

    result = service.get_weather()

    assert result["temperature"] == "--"
    assert result["description"] == "Error"
    assert result["humidity"] == "--"
    assert result["icon"] == "unknown"
    assert "time" in result


def test_get_air_quality_success(weather_service, weather_data):
    service, provider, _factory = weather_service
    provider.get_weather.return_value = weather_data

    assert service.get_air_quality() == {
        "aqi": 1,
        "aqi_label": "Good",
        "components": {"pm2_5": 4.11},
    }


def test_get_air_quality_without_data(weather_service, weather_data):
    service, provider, _factory = weather_service
    provider.get_weather.return_value = weather_data.model_copy(
        update={"air_quality": None}
    )

    assert service.get_air_quality() is None
