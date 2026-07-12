import json
import threading
from datetime import datetime

from ynab_budget import (
    YnabBudgetClient,
    YnabSnapshot,
    configured_views,
    view_at,
)

RAW = {
    "data": {
        "month": {
            "month": "2026-07-01",
            "currency_format": {"currency_symbol": "€"},
            "categories": [
                {
                    "name": "Dining",
                    "category_group_name": "Food",
                    "budgeted": 400000,
                    "activity": -82500,
                    "balance": 500000,
                    "hidden": False,
                    "deleted": False,
                },
                {
                    "name": "Old",
                    "category_group_name": "Food",
                    "budgeted": 1000,
                    "activity": 0,
                    "balance": 1000,
                    "hidden": True,
                    "deleted": False,
                },
            ],
        }
    }
}


def test_snapshot_normalizes_milliunits_and_excludes_hidden():
    payload = YnabBudgetClient._normalize(RAW)
    snapshot = YnabSnapshot.from_dict(payload)
    dining = snapshot.category("dining")
    assert len(snapshot.categories) == 1
    assert dining.assigned == 400
    assert dining.spent == 82.5
    assert dining.assigned_remaining == 317.5


def test_client_uses_last_good_cache_when_refresh_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("ynab_enabled", "true")
    monkeypatch.setenv("ynab_cache_file", str(tmp_path / "ynab.json"))
    client = YnabBudgetClient()
    normalized = client._normalize(RAW)
    client.cache_file.write_text(json.dumps(normalized))

    def fail_request():
        raise OSError("offline")

    monkeypatch.setattr(client, "_request", fail_request)
    snapshot = client.get_snapshot(force=True)
    assert snapshot is not None
    assert snapshot.stale is True


def test_views_are_filtered_and_rotate(monkeypatch):
    monkeypatch.setenv("ynab_views", "daily,unknown,active")
    monkeypatch.setenv("ynab_view_duration", "60")
    assert configured_views() == ["daily", "active"]
    assert view_at(datetime.fromtimestamp(0), ["daily", "active"]) == "daily"
    assert view_at(datetime.fromtimestamp(60), ["daily", "active"]) == "active"


def test_concurrent_snapshot_requests_share_one_refresh(monkeypatch, tmp_path):
    monkeypatch.setenv("ynab_enabled", "true")
    monkeypatch.setenv("ynab_cache_file", str(tmp_path / "ynab.json"))
    client = YnabBudgetClient()
    request_started = threading.Event()
    release_request = threading.Event()
    request_count = 0

    def request():
        nonlocal request_count
        request_count += 1
        request_started.set()
        assert release_request.wait(timeout=2)
        return RAW

    monkeypatch.setattr(client, "_request", request)
    results = []

    def get_snapshot():
        results.append(client.get_snapshot())

    first = threading.Thread(target=get_snapshot)
    second = threading.Thread(target=get_snapshot)

    first.start()
    assert request_started.wait(timeout=2)
    second.start()
    release_request.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert request_count == 1
    assert len(results) == 2
    assert results[0] is results[1]


def test_failed_refresh_is_throttled_without_cached_snapshot(monkeypatch, tmp_path):
    monkeypatch.setenv("ynab_enabled", "true")
    monkeypatch.setenv("ynab_cache_file", str(tmp_path / "missing.json"))
    client = YnabBudgetClient()
    request_count = 0

    def fail_request():
        nonlocal request_count
        request_count += 1
        raise OSError("offline")

    monkeypatch.setattr(client, "_request", fail_request)

    assert client.get_snapshot() is None
    assert client.get_snapshot() is None
    assert request_count == 1
