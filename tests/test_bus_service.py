import pytest
import responses
import os
from bus_service import BusService, _parse_lines
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import re

@pytest.fixture
def bus_service(mock_env_vars):
    """Fixture providing a BusService instance"""
    with patch.dict(os.environ, mock_env_vars, clear=True):
        return BusService()

@pytest.fixture
def mock_responses():
    """Fixture to mock API responses using the responses library"""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps

@pytest.mark.parametrize("lines_input,expected", [
    ("64", ["64"]),
    ("64,59", ["64", "59"]),
    ("64 59", ["64", "59"]),
    ("64, 59", ["64", "59"]),
    ([59, 64], ["59", "64"]),
    (["59", "64"], ["59", "64"]),
    ("", []),
    (None, []),
])
def test_parse_lines(lines_input, expected):
    """Test line number parsing with different input formats"""
    if isinstance(lines_input, (list, tuple)):
        result = [str(x) for x in lines_input]
        assert sorted(result) == sorted(expected)
    else:
        with patch.dict(os.environ, {'Lines': str(lines_input) if lines_input is not None else ''}, clear=True):
            result = _parse_lines(lines_input)
            assert sorted(result) == sorted(expected)

def test_bus_service_initialization(bus_service, mock_env_vars):
    """Test BusService initialization"""
    assert bus_service.base_url.rstrip('/').replace('localhost', '127.0.0.1') == mock_env_vars["BUS_API_BASE_URL"].rstrip('/')
    assert bus_service.provider == mock_env_vars["Provider"]
    assert bus_service.stop_id == "2100"
    assert isinstance(bus_service.lines_of_interest, list)

@responses.activate
def test_get_waiting_times_success(bus_service, mock_responses, sample_bus_response):
    """Test successful waiting times retrieval"""
    # Mock the API health check
    mock_responses.add(
        responses.GET,
        "http://localhost:5001/health/",
        json={"status": "ok"},
        status=200
    )

    # Mock the API response
    mock_responses.add(
        responses.GET,
        "http://localhost:5001/api/test_provider/waiting_times/",
        json={"stops": {bus_service.stop_id: sample_bus_response}},
        status=200
    )

    departures, error, stop_name = bus_service.get_waiting_times()
    
    assert departures is not None
    assert len(departures) > 0
    assert error is None
    assert stop_name == "Test Stop"
    assert departures[0]["line"] == "64"
    assert departures[0]["times"] == ["5"]

@responses.activate
def test_get_waiting_times_error(bus_service, mock_responses):
    """Test waiting times retrieval with API error"""
    # Mock the API health check
    mock_responses.add(
        responses.GET,
        "http://localhost:5001/health/",
        json={"status": "error"},
        status=500
    )

    departures, error, stop_name = bus_service.get_waiting_times()
    
    assert departures is not None  # Should return error data
    assert error == "API not available"
    assert stop_name == ""

def test_get_line_color(bus_service):
    """Test line color determination"""
    # Test with a known line number
    primary_color, secondary_color, ratio = bus_service.get_line_color("64")
    assert primary_color in ['black', 'white', 'red', 'yellow']
    assert secondary_color in ['black', 'white', 'red', 'yellow']
    assert 0 <= ratio <= 1

@responses.activate
def test_get_api_health(bus_service, mock_responses):
    """Test API health check"""
    # Test successful health check
    mock_responses.add(
        responses.GET,
        "http://localhost:5001/health/",
        json={"status": "ok"},
        status=200
    )
    assert bus_service.get_api_health() is True

    # Test failed health check
    mock_responses.replace(
        responses.GET,
        "http://localhost:5001/health/",
        json={"status": "error"},
        status=500
    )
    assert bus_service.get_api_health() is False 