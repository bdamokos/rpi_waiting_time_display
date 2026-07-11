import iss
from datetime import datetime, timezone

from PIL import Image

from display_adapter import MockDisplay


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


def test_next_known_pass_skips_started_predictions():
    tracker = iss.ISSTracker()
    tracker.next_passes = [
        {"risetime": 99, "duration": 60},
        {"risetime": 200, "duration": 60},
    ]

    assert tracker.next_known_pass(now=100) == tracker.next_passes[1]
    assert tracker.next_known_pass(now=201) is None


def test_next_known_pass_accepts_datetime():
    tracker = iss.ISSTracker()
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    tracker.next_passes = [
        {"risetime": int(now.timestamp()) + 60, "duration": 60},
    ]

    assert tracker.next_known_pass(now=now) == tracker.next_passes[0]


def test_prediction_and_empty_state_render_at_display_dimensions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    display = MockDisplay()
    now = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)
    prediction = {
        "risetime": int(now.timestamp()) + 3700,
        "duration": 362,
        "position": {"max": {"direction": "SE", "altitude": 48.2}},
        "darkness": {"fully_dark": True},
    }

    iss.display_next_iss_pass(display, prediction, now=now)
    assert Image.open("debug_output.png").size == (display.height, display.width)

    iss.display_next_iss_pass(display, None, now=now)
    assert Image.open("debug_output.png").size == (display.height, display.width)


def test_prediction_handles_naive_now_and_partial_fields(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    display = MockDisplay()
    now = datetime(2026, 7, 11, 12, 0)
    prediction = {
        "risetime": int(now.astimezone().timestamp()) + 600,
        "duration": 120,
        "position": None,
        "darkness": None,
    }

    iss.display_next_iss_pass(display, prediction, now=now)
    iss.display_next_iss_pass(display, {}, now=now)
    assert Image.open("debug_output.png").size == (display.height, display.width)
