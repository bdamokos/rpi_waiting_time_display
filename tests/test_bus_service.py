from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from bus_service import BusService, _parse_lines


def make_response(*, status=200, data=None, error=None):
    response = MagicMock()
    response.status_code = status
    response.text = ""
    response.elapsed.total_seconds.return_value = 0.01
    response.json.return_value = data
    response.raise_for_status.side_effect = error
    return response


@pytest.fixture
def bus_service(mock_env_vars):
    with (
        patch.dict("os.environ", mock_env_vars, clear=True),
        patch("bus_service.Stop", mock_env_vars["Stops"]),
        patch("bus_service.Lines", mock_env_vars["Lines"]),
        patch("bus_service.bus_api_base_url", mock_env_vars["BUS_API_BASE_URL"]),
        patch("bus_service.bus_schedule_url", mock_env_vars["BUS_API_BASE_URL"]),
        patch.object(BusService, "_start_health_check"),
    ):
        return BusService()


@pytest.mark.parametrize(
    "lines_input,expected",
    [
        ("64", ["64"]),
        ("64,59", ["64", "59"]),
        ("64 59", ["64", "59"]),
        ("64, 59", ["64", "59"]),
        ([59, 64], ["59", "64"]),
        (["59", "64"], ["59", "64"]),
        ("", []),
        (None, []),
    ],
)
def test_parse_lines(lines_input, expected):
    if isinstance(lines_input, (list, tuple)):
        result = [str(x) for x in lines_input]
    else:
        result = _parse_lines(lines_input)
    assert sorted(result) == sorted(expected)


def test_bus_service_initialization(bus_service, mock_env_vars):
    assert bus_service.base_url == mock_env_vars["BUS_API_BASE_URL"].rstrip("/")
    assert bus_service.provider == mock_env_vars["Provider"]
    assert bus_service.stop_id == mock_env_vars["Stops"]
    assert bus_service.lines_of_interest == ["64"]


def test_get_waiting_times_success(bus_service, sample_bus_response):
    response = make_response(data={"stops": {bus_service.stop_id: sample_bus_response}})

    with patch("bus_service.requests.get", return_value=response) as request:
        departures, error, stop_name = bus_service.get_waiting_times()

    request.assert_called_once_with(bus_service.api_url, timeout=120)
    assert error is None
    assert stop_name == "Test Stop"
    assert departures[0]["line"] == "64"
    assert departures[0]["times"] == ["5"]


def test_get_waiting_times_backoff_and_recovery(bus_service, sample_bus_response):
    failure = make_response(status=500, error=RuntimeError("API unavailable"))

    with patch("bus_service.requests.get", return_value=failure) as request:
        departures, error, stop_name = bus_service.get_waiting_times()

        assert departures
        assert error == "Service error"
        assert stop_name == ""
        assert bus_service._fallback_backoff.get_failure_count() == 1

        first_retry = bus_service._fallback_backoff._next_retry_time
        _departures, error, _stop_name = bus_service.get_waiting_times()
        assert "Next attempt at" in error
        assert request.call_count == 1

        bus_service._fallback_backoff._next_retry_time = datetime.now() - timedelta(
            seconds=1
        )
        bus_service.get_waiting_times()
        assert bus_service._fallback_backoff.get_failure_count() == 2
        assert bus_service._fallback_backoff._next_retry_time > first_retry

        success = make_response(
            data={"stops": {bus_service.stop_id: sample_bus_response}}
        )
        request.return_value = success
        bus_service._fallback_backoff._next_retry_time = datetime.now() - timedelta(
            seconds=1
        )
        bus_service.get_waiting_times()

    assert bus_service._fallback_backoff.get_failure_count() == 0
    assert bus_service._fallback_backoff._next_retry_time is None


def test_get_line_color_without_display(bus_service):
    colors = bus_service.get_line_color("64")

    assert colors == [("black", 0.7), ("white", 0.3)]


def test_get_api_health(bus_service):
    with patch(
        "bus_service.requests.get",
        return_value=make_response(status=200, data={"status": "ok"}),
    ):
        assert bus_service.get_api_health() is True

    with patch(
        "bus_service.requests.get",
        return_value=make_response(status=500, data={"status": "error"}),
    ):
        assert bus_service.get_api_health() is False
