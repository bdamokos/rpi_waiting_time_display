import json

import pytest

from display_runtime_health import DisplayHealthReporter, instrument_display


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


def test_reporter_writes_only_completed_state_changes(tmp_path):
    path = tmp_path / "client-health.json"
    clock = Clock()
    reporter = DisplayHealthReporter(path, clock=clock, pid=42, boot_id="boot")
    initial = path.read_text()

    clock.value = 1001.0
    reporter.mark_attempt("displayPartial")
    assert path.read_text() == initial

    clock.value = 1002.0
    reporter.mark_success("displayPartial")
    payload = json.loads(path.read_text())
    assert payload["sequence"] == 1
    assert payload["last_success_at"] == 1002.0
    assert payload["in_progress"] is False
    assert payload["role"] == "display-client"


def test_instrumented_display_reports_success_and_failure(tmp_path):
    class Display:
        def __init__(self):
            self.fail = False

        def display(self, image):
            if self.fail:
                raise RuntimeError("SPI busy")
            return image

    clock = Clock()
    reporter = DisplayHealthReporter(tmp_path / "health.json", clock=clock)
    display = instrument_display(Display(), reporter)

    assert display.display("frame") == "frame"
    assert reporter.snapshot()["sequence"] == 1

    display.fail = True
    clock.value += 1
    with pytest.raises(RuntimeError, match="SPI busy"):
        display.display("frame")
    snapshot = reporter.snapshot()
    assert snapshot["sequence"] == 1
    assert snapshot["last_error"].startswith("RuntimeError: SPI busy")


def test_server_freshness_fields_share_the_runtime_contract(tmp_path):
    clock = Clock(1500.0)
    reporter = DisplayHealthReporter(tmp_path / "health.json", clock=clock)
    reporter.mark_server_frame(1490.0)
    payload = json.loads((tmp_path / "health.json").read_text())
    assert payload["server_generated_at"] == 1490.0
    assert payload["server_received_at"] == 1500.0
