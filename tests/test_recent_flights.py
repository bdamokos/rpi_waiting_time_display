from datetime import datetime
from threading import Lock, RLock
from unittest.mock import Mock, patch

from display_adapter import MockDisplay
from flights import RecentFlightCache, update_display_with_recent_flights
from screen_arbiter import ScreenArbiter


def test_recent_flight_cache_is_bounded_deduplicated_and_newest_first():
    cache = RecentFlightCache(max_entries=2)
    cache.record({"hex": "a", "callsign": "ONE"}, datetime(2026, 7, 11, 9, 0))
    cache.record({"hex": "b", "callsign": "TWO"}, datetime(2026, 7, 11, 9, 1))
    cache.record({"hex": "a", "callsign": "ONE2"}, datetime(2026, 7, 11, 9, 2))
    cache.record({"hex": "c", "callsign": "THREE"}, datetime(2026, 7, 11, 9, 3))

    recent = cache.recent()

    assert [flight["callsign"] for flight in recent] == ["THREE", "ONE2"]
    assert recent[1]["observed_at"] == datetime(2026, 7, 11, 9, 2)


def test_recent_flight_cache_rejects_entries_without_an_identifier():
    cache = RecentFlightCache()

    assert not cache.record({"origin_code": "BRU"})
    assert cache.recent() == []


def test_recent_flights_renderer_handles_partial_and_missing_route_data(monkeypatch):
    display = MockDisplay()
    displayed = []
    monkeypatch.setattr(display, "displayPartBaseImage", displayed.append)

    assert update_display_with_recent_flights(
        display,
        [
            {
                "callsign": "BEL123",
                "origin_code": "BRU",
                "destination_code": "LHR",
                "observed_at": datetime(2026, 7, 11, 9, 5),
            },
            {"registration": "OO-ABC", "observed_at": datetime(2026, 7, 11, 9, 4)},
        ],
        set_base_image=True,
    )
    assert len(displayed) == 1


def test_flights_override_uses_cache_without_displacing_live_flight():
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.epd = Mock()
    manager.recent_flights = RecentFlightCache()
    manager.recent_flights.record(
        {"callsign": "BEL123", "origin_code": "BRU", "destination_code": "LHR"}
    )
    manager.screen_arbiter = ScreenArbiter()
    manager.override_priority = 30
    manager.override_duration_seconds = 300
    manager._override_module = None
    manager._override_generation = 0
    manager._override_lock = RLock()
    manager._override_render_lock = Lock()
    manager._display_lock = Lock()
    manager.current_display_mode = None
    manager.current_token_view = None
    manager.in_weather_mode = False
    manager.last_display_update = None

    with patch("basic.update_display_with_recent_flights", return_value=True) as render:
        result = manager.request_display_override("flights")

        assert result["rendered"]
        render.assert_called_once()

        manager.screen_arbiter.claim(manager.FLIGHT_SCREEN_OWNER, 50, 30)
        assert manager.screen_arbiter.active_owner() == manager.FLIGHT_SCREEN_OWNER
        assert not manager._render_display_override()
        render.assert_called_once()


def test_empty_flights_override_releases_screen_claim():
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.epd = Mock()
    manager.recent_flights = RecentFlightCache()
    manager.screen_arbiter = ScreenArbiter()
    manager.override_priority = 30
    manager.override_duration_seconds = 300
    manager._override_module = None
    manager._override_generation = 0
    manager._override_lock = RLock()
    manager._override_render_lock = Lock()
    manager._display_lock = Lock()
    restored = []
    manager._force_display_update = lambda: restored.append(True)

    result = manager.request_display_override("flights")

    assert result["accepted"]
    assert not result["rendered"]
    assert result["active_owner"] is None
    assert manager._override_module is None
    assert restored == [True]
