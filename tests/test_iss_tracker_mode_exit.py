import iss


def test_on_pass_end_called_even_if_monitor_pass_raises(monkeypatch):
    tracker = iss.ISSTracker()

    tracker.prediction_interval = 10**9
    tracker.last_prediction_time = 10**9

    now = 1_000_000
    monkeypatch.setattr(iss, "time", lambda: now)

    tracker.next_passes = [
        {
            "risetime": now - 1,
            "duration": 60,
        }
    ]

    def _boom(pass_info, epd):
        raise RuntimeError("boom")

    monkeypatch.setattr(tracker, "monitor_pass", _boom)

    called = {"start": 0, "end": 0}

    def on_pass_start():
        called["start"] += 1

    def on_pass_end():
        called["end"] += 1
        tracker.stop_event.set()

    tracker.run(epd=None, on_pass_start=on_pass_start, on_pass_end=on_pass_end)

    assert called["start"] == 1
    assert called["end"] == 1

