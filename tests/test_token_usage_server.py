from tools.token_usage_server import SnapshotBuilder


def test_bridge_normalizes_and_removes_identity_fields(monkeypatch):
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
    builder = SnapshotBuilder("codexbar", 300)

    def fake_run(*arguments):
        return usage if arguments[0] == "usage" else cost

    monkeypatch.setattr(builder, "_run", fake_run)
    monkeypatch.setattr("tools.token_usage_server.datetime", _JulyDatetime)
    snapshot = builder.build()
    serialized = str(snapshot).lower()
    assert snapshot["limits"]["primary"]["used_percent"] == 25
    assert snapshot["month_to_date"]["cost_usd"] == 12.5
    assert "email" not in serialized
    assert "project" not in serialized


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
