from datetime import datetime
from unittest.mock import Mock, patch

from display_adapter import MockDisplay
from flight_statistics import (
    FlightStatisticsStore,
    _record_rows,
    update_display_with_flight_records,
    update_display_with_flight_statistics,
)
from screen_arbiter import ScreenArbiter


def _flight(hex_id, **values):
    return {"hex": hex_id, "callsign": values.pop("callsign", hex_id.upper()), **values}


def test_store_deduplicates_one_pass_but_counts_a_returning_plane(tmp_path):
    store = FlightStatisticsStore(
        tmp_path / "flights.sqlite3",
        encounter_gap_minutes=30,
        update_interval_seconds=10,
    )
    store.record(
        _flight(
            "abc",
            origin_code="BRU",
            destination_code="LHR",
            operator="Brussels Airlines",
            last_distance=2.4,
        ),
        datetime(2026, 7, 14, 9, 0),
    )
    store.record(
        _flight("abc", registration="OO-ABC", last_distance=1.2),
        datetime(2026, 7, 14, 9, 5),
    )
    store.record(
        _flight("abc", registration="OO-ABC", last_distance=1.8),
        datetime(2026, 7, 14, 10, 0),
    )

    summary = store.summary("day", now=datetime(2026, 7, 14, 12, 0))
    records = store.records(now=datetime(2026, 7, 14, 12, 0))

    assert summary["encounters"] == 2
    assert summary["unique_aircraft"] == 1
    assert summary["top_routes"] == [("BRU>LHR", 1)]
    assert summary["top_operators"] == [("Brussels Airlines", 1)]
    assert summary["repeat"] == ("OO-ABC", 2)
    assert records["closest"] == ("OO-ABC", 1.2)


def test_store_preserves_falsy_identifiers(tmp_path):
    store = FlightStatisticsStore(tmp_path / "flights.sqlite3")

    assert store.record({"callsign": 0}, datetime(2026, 7, 14, 9, 0))
    summary = store.summary("day", datetime(2026, 7, 14, 12))
    assert summary["encounters"] == 1
    assert summary["repeat"] is None


def test_calendar_periods_and_fun_records_use_available_metadata(tmp_path):
    store = FlightStatisticsStore(tmp_path / "flights.sqlite3")
    observations = [
        (
            datetime(2026, 6, 30, 8),
            _flight("old", registration="OO-OLD", aircraft_year=1998),
        ),
        (
            datetime(2026, 7, 13, 8),
            _flight(
                "old",
                registration="OO-OLD",
                aircraft_year=1998,
                origin_code="BRU",
                destination_code="MAD",
                operator_name="Air Example",
            ),
        ),
        (
            datetime(2026, 7, 14, 10),
            _flight(
                "new",
                registration="OO-NEW",
                aircraft_year=2024,
                origin_code="BRU",
                destination_code="MAD",
                operator_name="Air Example",
                ground_speed=440,
            ),
        ),
    ]
    for observed_at, flight in observations:
        store.record(flight, observed_at)

    now = datetime(2026, 7, 14, 12)
    assert store.summary("day", now)["encounters"] == 1
    assert store.summary("week", now)["encounters"] == 2
    assert store.summary("month", now)["top_routes"] == [("BRU>MAD", 2)]
    records = store.records(now)
    assert records["oldest"] == {"label": "OO-OLD", "year": 1998}
    assert records["youngest"] == {"label": "OO-NEW", "year": 2024}
    assert records["repeat"] == ("OO-OLD", 2)
    assert records["fastest"] == ("OO-NEW", 440.0)


def test_statistics_renderers_handle_rich_data(monkeypatch):
    display = MockDisplay()
    displayed = []
    monkeypatch.setattr(display, "displayPartBaseImage", displayed.append)
    summary = {
        "label": "This week",
        "encounters": 12,
        "unique_aircraft": 8,
        "top_routes": [("BRU>LHR", 4)],
        "top_operators": [("Brussels Airlines", 5)],
        "top_types": [("Airbus A320", 4)],
        "repeat": ("OO-ABC", 3),
        "busiest_hour": (9, 4),
    }
    records = {
        "encounters": 12,
        "oldest": {"label": "OO-OLD", "year": 1998},
        "youngest": {"label": "OO-NEW", "year": 2024},
        "repeat": ("OO-ABC", 3),
        "closest": ("OO-NEAR", 0.8),
        "fastest": ("OO-FAST", 475),
    }

    assert update_display_with_flight_statistics(display, summary, set_base_image=True)
    assert update_display_with_flight_records(display, records, set_base_image=True)
    assert len(displayed) == 2
    assert _record_rows(records)[-1] == ("Fastest", "OO-FAST", "475 kt")


def test_week_statistics_override_uses_persisted_store():
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.epd = Mock()
    manager.flight_statistics = Mock()
    manager.flight_statistics.summary.return_value = {"label": "This week"}
    manager.screen_arbiter = ScreenArbiter()
    manager.override_priority = 30
    manager.override_duration_seconds = 300
    manager._override_module = None
    manager._override_generation = 0
    import threading

    manager._override_lock = threading.RLock()
    manager._override_render_lock = threading.Lock()
    manager._display_lock = threading.Lock()
    manager.current_display_mode = None
    manager.current_token_view = None
    manager.in_weather_mode = False
    manager.last_display_update = None

    with patch(
        "basic.update_display_with_flight_statistics", return_value=True
    ) as render:
        result = manager.request_display_override("flight_stats")

    assert result["module"] == "flight_stats_week"
    assert result["rendered"]
    render.assert_called_once()


def test_statistics_failure_does_not_block_recent_flight_history():
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.recent_flights = Mock()
    manager.flight_statistics = Mock()
    manager.flight_statistics.record.side_effect = ValueError("bad statistics row")
    flight = {"hex": "abc"}
    observed_at = datetime(2026, 7, 14, 9, 0)

    manager._record_flight_observation(flight, observed_at)

    manager.recent_flights.record.assert_called_once_with(
        flight, observed_at=observed_at
    )
