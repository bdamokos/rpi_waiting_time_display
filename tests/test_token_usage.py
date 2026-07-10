import json
from datetime import datetime

import pytest

from token_usage import (
    DisplaySchedule,
    TokenUsageClient,
    TokenUsageSnapshot,
    token_view_at,
)


SAMPLE = {
    "generated_at": "2026-07-10T12:00:00+02:00",
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
        "transit@06:00-09:00,token@09:00-22:00,weather@22:00-06:00"
    )
    assert schedule.mode_at(datetime(2026, 7, 10, 8, 59)) == "transit"
    assert schedule.mode_at(datetime(2026, 7, 10, 9, 0)) == "token"
    assert schedule.mode_at(datetime(2026, 7, 10, 23, 0)) == "weather"
    assert schedule.mode_at(datetime(2026, 7, 10, 5, 59)) == "weather"


def test_invalid_schedule_is_rejected():
    with pytest.raises(ValueError):
        DisplaySchedule("private-mode@09:00-10:00")


def test_snapshot_reports_remaining_capacity():
    snapshot = TokenUsageSnapshot.from_dict(SAMPLE)
    assert snapshot.primary.remaining_percent == 82
    assert snapshot.secondary.remaining_percent == 55
    assert snapshot.month_cost_usd == 123.5


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


def test_view_rotation_uses_configured_duration(monkeypatch):
    monkeypatch.setenv("token_usage_view_duration", "300")
    views = ["month", "limits"]
    first = datetime.fromtimestamp(600)
    second = datetime.fromtimestamp(900)
    assert token_view_at(first, views) != token_view_at(second, views)
