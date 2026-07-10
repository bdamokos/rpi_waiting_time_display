import os

from tools.token_usage_server import RecentJsonActivity, SnapshotBuilder


def test_bridge_normalizes_and_removes_identity_fields(monkeypatch, tmp_path):
    usage = [
        {
            "provider": "codex",
            "usage": {
                "accountEmail": "private@example.test",
                "primary": {"usedPercent": 25, "resetsAt": "2026-07-10T15:00:00Z"},
                "secondary": {"usedPercent": 40, "resetsAt": "2026-07-14T15:00:00Z"},
            },
        }
    ]
    cost = [
        {
            "currencyCode": "USD",
            "daily": [
                {
                    "date": "2026-07-10",
                    "totalCost": 12.5,
                    "totalTokens": 3_000_000,
                    "projects": ["private-project"],
                }
            ],
        }
    ]
    activity_file = tmp_path / "session.jsonl"
    activity_file.write_text("{}\n", encoding="utf-8")
    builder = SnapshotBuilder(
        "codexbar", 300, RecentJsonActivity([tmp_path], 300)
    )

    def fake_run(*arguments):
        return usage if arguments[0] == "usage" else cost

    monkeypatch.setattr(builder, "_run", fake_run)
    monkeypatch.setattr("tools.token_usage_server.datetime", _JulyDatetime)
    snapshot = builder.build()
    serialized = str(snapshot).lower()
    assert snapshot["limits"]["primary"]["used_percent"] == 25
    assert snapshot["month_to_date"]["cost_usd"] == 12.5
    assert snapshot["active"] is True
    assert "email" not in serialized
    assert "project" not in serialized


def test_recent_json_activity_uses_modification_window(tmp_path):
    session = tmp_path / "sessions" / "session.jsonl"
    session.parent.mkdir()
    session.write_text("{}\n", encoding="utf-8")
    detector = RecentJsonActivity([session.parent], 300)

    os.utime(session, (699, 699))
    assert detector.is_active(now=1000) is False
    os.utime(session, (700, 700))
    assert detector.is_active(now=1000) is True


def test_activity_is_rechecked_while_usage_metrics_are_cached(monkeypatch):
    class ActivityDetector:
        def __init__(self):
            self.active = True

        def is_active(self):
            return self.active

    detector = ActivityDetector()
    builder = SnapshotBuilder("codexbar", 300, detector)
    monkeypatch.setattr(
        builder,
        "_run",
        lambda *arguments: (
            [{"usage": {}}]
            if arguments[0] == "usage"
            else [{"currencyCode": "USD", "daily": []}]
        ),
    )

    assert builder.build()["active"] is True
    detector.active = False
    assert builder.build()["active"] is False


class _JulyDatetime:
    @classmethod
    def now(cls):
        return cls()

    def strftime(self, value):
        return "2026-07-"

    def astimezone(self):
        return self

    def isoformat(self):
        return "2026-07-10T12:00:00+02:00"
