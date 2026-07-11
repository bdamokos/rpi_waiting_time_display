import json
from datetime import datetime

from ynab_budget import (YnabBudgetClient, YnabSnapshot, configured_views,
                         view_at)

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
    monkeypatch.setattr(
        client, "_request", lambda: (_ for _ in ()).throw(OSError("offline"))
    )
    snapshot = client.get_snapshot(force=True)
    assert snapshot is not None
    assert snapshot.stale is True


def test_views_are_filtered_and_rotate(monkeypatch):
    monkeypatch.setenv("ynab_views", "daily,unknown,active")
    monkeypatch.setenv("ynab_view_duration", "60")
    assert configured_views() == ["daily", "active"]
    assert view_at(datetime.fromtimestamp(0), ["daily", "active"]) == "daily"
    assert view_at(datetime.fromtimestamp(60), ["daily", "active"]) == "active"
