import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from token_usage import (
    DisplaySchedule,
    TokenUsageClient,
    TokenUsageSnapshot,
    token_view_at,
)


SAMPLE = {
    "generated_at": "2026-07-10T12:00:00+02:00",
    "active": True,
    "currency": "USD",
    "limits": {
        "primary": {"used_percent": 18, "resets_at": "2026-07-10T15:00:00Z"},
        "secondary": {"used_percent": 45, "resets_at": "2026-07-14T15:00:00Z"},
    },
    "month_to_date": {"cost_usd": 123.5, "total_tokens": 234_000_000},
    "daily": [
        {"date": "2026-07-09", "cost_usd": 40, "total_tokens": 80_000_000},
        {"date": "2026-07-10", "cost_usd": 83.5, "total_tokens": 154_000_000},
    ],
}


def test_schedule_selects_day_and_overnight_ranges():
    schedule = DisplaySchedule(
        "transit@06:00-10:00,token@10:00-22:00,weather@22:00-06:00"
    )
    assert schedule.mode_at(datetime(2026, 7, 10, 9, 59)) == "transit"
    assert schedule.mode_at(datetime(2026, 7, 10, 10, 0)) == "token"
    assert schedule.mode_at(datetime(2026, 7, 10, 23, 0)) == "weather"
    assert schedule.mode_at(datetime(2026, 7, 10, 5, 59)) == "weather"


def test_schedule_supports_weekday_and_weekend_overrides():
    schedule = DisplaySchedule(
        "token-always@weekends@00:00-00:00,"
        "transit@weekdays@06:00-10:00,"
        "token@weekdays@10:00-22:00,"
        "weather@weekdays@22:00-06:00"
    )
    assert schedule.mode_at(datetime(2026, 7, 10, 9, 59)) == "transit"  # Friday
    assert schedule.mode_at(datetime(2026, 7, 10, 10, 0)) == "token"
    assert schedule.mode_at(datetime(2026, 7, 11, 1, 0)) == "token-always"  # Saturday
    assert schedule.mode_at(datetime(2026, 7, 12, 23, 59)) == "token-always"
    assert schedule.mode_at(datetime(2026, 7, 13, 1, 0)) == "weather"  # Monday


def test_schedule_supports_day_lists_and_wrapping_ranges():
    schedule = DisplaySchedule("token@fri-mon+wed@12:00-13:00")
    for day in (10, 11, 12, 13, 15):
        assert schedule.mode_at(datetime(2026, 7, day, 12, 0)) == "token"
    assert schedule.mode_at(datetime(2026, 7, 14, 12, 0)) == "auto"


def test_invalid_schedule_is_rejected():
    with pytest.raises(ValueError):
        DisplaySchedule("private-mode@09:00-10:00")
    with pytest.raises(ValueError):
        DisplaySchedule("token@funday@09:00-10:00")


def test_snapshot_reports_remaining_capacity():
    snapshot = TokenUsageSnapshot.from_dict(SAMPLE)
    assert snapshot.active is True
    assert snapshot.primary.remaining_percent == 82
    assert snapshot.secondary.remaining_percent == 55
    assert snapshot.month_cost_usd == 123.5


def test_snapshot_without_explicit_activity_is_inactive():
    payload = {key: value for key, value in SAMPLE.items() if key != "active"}
    assert TokenUsageSnapshot.from_dict(payload).active is False


def test_scheduled_token_mode_requires_live_activity(monkeypatch):
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.display_schedule = DisplaySchedule("token@00:00-00:00")
    manager.token_usage_client = SimpleNamespace(
        enabled=True,
        get_snapshot=lambda: SimpleNamespace(active=False, stale=False),
    )
    monkeypatch.setenv("token_usage_fallback_mode", "weather")
    now = datetime(2026, 7, 10, 12, 0)

    assert manager._scheduled_mode(now) == "weather"
    manager.token_usage_client.get_snapshot = lambda: SimpleNamespace(
        active=True, stale=False
    )
    assert manager._scheduled_mode(now) == "token"
    manager.token_usage_client.get_snapshot = lambda: SimpleNamespace(
        active=True, stale=True
    )
    assert manager._scheduled_mode(now) == "weather"
    monkeypatch.setenv("token_usage_fallback_mode", "token")
    assert manager._scheduled_mode(now) == "transit"


def test_token_always_mode_ignores_activity_but_not_staleness(monkeypatch):
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.display_schedule = DisplaySchedule("token-always@weekends@00:00-00:00")
    manager.token_usage_client = SimpleNamespace(
        enabled=True,
        get_snapshot=lambda: SimpleNamespace(active=False, stale=False),
    )
    monkeypatch.setenv("token_usage_fallback_mode", "weather")

    assert manager._scheduled_mode(datetime(2026, 7, 11, 12, 0)) == "token-always"
    manager.token_usage_client.get_snapshot = lambda: SimpleNamespace(
        active=False, stale=True
    )
    assert manager._scheduled_mode(datetime(2026, 7, 11, 12, 0)) == "weather"


def test_file_client_reads_and_caches_snapshot(tmp_path, monkeypatch):
    source = tmp_path / "snapshot.json"
    source.write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setenv("token_usage_enabled", "true")
    monkeypatch.setenv("token_usage_source", "file")
    monkeypatch.setenv("token_usage_file", str(source))
    monkeypatch.setenv("token_usage_cache_file", str(tmp_path / "cache.json"))
    client = TokenUsageClient()
    snapshot = client.get_snapshot()
    assert snapshot.month_tokens == 234_000_000
    source.unlink()
    assert client.get_snapshot() is snapshot


def test_client_discards_cache_after_maximum_stale_age(tmp_path, monkeypatch):
    source = tmp_path / "snapshot.json"
    cache = tmp_path / "cache.json"
    source.write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setenv("token_usage_enabled", "true")
    monkeypatch.setenv("token_usage_source", "file")
    monkeypatch.setenv("token_usage_file", str(source))
    monkeypatch.setenv("token_usage_cache_file", str(cache))
    monkeypatch.setenv("token_usage_max_stale_seconds", "0")
    client = TokenUsageClient()
    assert client.get_snapshot() is not None
    source.unlink()
    assert client.get_snapshot(force=True) is None


def test_client_does_not_trust_stale_active_status(tmp_path, monkeypatch):
    source = tmp_path / "snapshot.json"
    cache = tmp_path / "cache.json"
    source.write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setenv("token_usage_enabled", "true")
    monkeypatch.setenv("token_usage_source", "file")
    monkeypatch.setenv("token_usage_file", str(source))
    monkeypatch.setenv("token_usage_cache_file", str(cache))
    client = TokenUsageClient()
    assert client.get_snapshot().active is True
    source.unlink()
    stale = client.get_snapshot(force=True)
    assert stale is not None
    assert stale.stale is True
    assert stale.active is False


def test_view_rotation_uses_configured_duration(monkeypatch):
    monkeypatch.setenv("token_usage_view_duration", "300")
    views = ["month", "limits"]
    first = datetime.fromtimestamp(600)
    second = datetime.fromtimestamp(900)
    assert token_view_at(first, views) != token_view_at(second, views)
