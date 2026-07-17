import hashlib
import io
import json
import socket
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
import requests
from PIL import Image

from display_client import (
    ClientHealth,
    FrameClient,
    HealthReporter,
    OutageDiagnosticController,
    SystemdNotifier,
    bounded_env_seconds,
    build_diagnostic_view,
    categorize_poll_error,
    clock_sync_marker_present,
)

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def png_bytes():
    output = io.BytesIO()
    Image.new("1", (250, 120), 1).save(output, "PNG")
    return output.getvalue()


class FakeResponse:
    def __init__(self, status=200, content=None, headers=None):
        self.status_code = status
        self.content = content or b""
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, headers, timeout, stream):
        self.calls.append((url, headers, timeout, stream))
        return self.responses.pop(0)


class FakeDisplay:
    def __init__(self):
        self.buffers = []
        self.base = []
        self.partial = []
        self.events = []

    def init(self):
        self.events.append("init")

    def Clear(self):
        self.events.append("clear")

    def init_Fast(self):
        self.events.append("fast")

    def getbuffer(self, image):
        self.buffers.append(image.copy())
        return image

    def displayPartBaseImage(self, image):
        self.base.append(image.copy())

    def displayPartial(self, image):
        self.partial.append(image.copy())


class MutableClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value


def frame_response(sequence=1, created_at=NOW, content=None):
    content = content or png_bytes()
    return FakeResponse(
        content=content,
        headers={
            "Content-Type": "image/png",
            "Content-Length": str(len(content)),
            "ETag": f'"{sequence}-etag"',
            "X-Display-Sequence": str(sequence),
            "X-Display-Published-At": created_at.isoformat(),
            "X-Display-SHA256": hashlib.sha256(content).hexdigest(),
        },
    )


def test_client_validates_displays_and_uses_conditional_request(monkeypatch):
    display = FakeDisplay()
    not_modified = FakeResponse(
        status=304,
        headers={"X-Display-Published-At": NOW.isoformat()},
    )
    session = FakeSession([frame_response(), not_modified])
    client = FrameClient(
        display,
        url="http://server/api/v1/frame.png",
        token="secret",
        session=session,
        clock=lambda: NOW,
    )

    assert client.poll_once().status == "displayed"
    assert display.base[0].size == (120, 250)
    assert client.poll_once().status == "not-modified"
    assert session.calls[1][1]["If-None-Match"] == '"1-etag"'
    assert session.calls[1][1]["Authorization"] == "Bearer secret"
    assert not_modified.closed


def test_client_pads_network_frame_to_physical_panel_width():
    display = FakeDisplay()
    display.width = 122
    display.height = 250
    client = FrameClient(
        display,
        url="http://server/api/v1/frame.png",
        session=FakeSession([frame_response()]),
        clock=lambda: NOW,
    )

    assert client.poll_once().status == "displayed"
    assert display.base[0].size == (122, 250)
    assert display.base[0].getpixel((0, 0)) == 1
    assert display.base[0].getpixel((121, 249)) == 1


def test_client_padding_preserves_multiband_image_mode():
    display = FakeDisplay()
    display.width = 122
    display.height = 250
    client = FrameClient(display, url="http://server/api/v1/frame.png")

    client._display(Image.new("RGB", (250, 120), (0, 0, 0)))

    assert display.base[0].mode == "RGB"
    assert display.base[0].getpixel((0, 0)) == (255, 255, 255)
    assert display.base[0].getpixel((121, 249)) == (255, 255, 255)


def test_client_rejects_not_modified_before_first_frame():
    response = FakeResponse(
        status=304,
        headers={"X-Display-Published-At": NOW.isoformat()},
    )
    client = FrameClient(
        FakeDisplay(),
        url="http://server/frame.png",
        session=FakeSession([response]),
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match="before a frame"):
        client.poll_once()
    assert response.closed


@pytest.mark.parametrize(
    "response, message",
    [
        (frame_response(created_at=NOW - timedelta(seconds=301)), "stale"),
        (
            FakeResponse(
                content=b"<html>error</html>",
                headers={
                    "Content-Type": "text/html",
                    "X-Display-Sequence": "1",
                    "X-Display-Published-At": NOW.isoformat(),
                },
            ),
            "content type",
        ),
    ],
)
def test_client_rejects_stale_or_non_png_without_touching_display(response, message):
    display = FakeDisplay()
    client = FrameClient(
        display,
        url="http://server/frame.png",
        session=FakeSession([response]),
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match=message):
        client.poll_once()
    assert not display.base
    assert not display.partial


def test_client_rejects_oversized_frame_before_reading_body():
    response = frame_response()
    response.headers["Content-Length"] = str(2 * 1024 * 1024 + 1)
    display = FakeDisplay()
    client = FrameClient(
        display,
        url="http://server/frame.png",
        session=FakeSession([response]),
        clock=lambda: NOW,
    )
    with pytest.raises(ValueError, match="exceeds"):
        client.poll_once()
    assert not display.base


def test_client_accepts_newer_frame_epoch_after_server_sequence_reset():
    display = FakeDisplay()
    session = FakeSession(
        [
            frame_response(sequence=10, created_at=NOW),
            frame_response(sequence=1, created_at=NOW + timedelta(seconds=1)),
        ]
    )
    client = FrameClient(
        display,
        url="http://server/frame.png",
        session=session,
        clock=lambda: NOW + timedelta(seconds=1),
    )
    client.poll_once()
    assert client.poll_once().sequence == 1
    assert len(display.partial) == 1


def test_client_periodically_uses_full_base_refresh(monkeypatch):
    monkeypatch.setenv("display_client_full_refresh_every", "2")
    display = FakeDisplay()
    session = FakeSession(
        [
            frame_response(sequence=1, created_at=NOW),
            frame_response(sequence=2, created_at=NOW + timedelta(seconds=1)),
            frame_response(sequence=3, created_at=NOW + timedelta(seconds=2)),
        ]
    )
    client = FrameClient(
        display,
        url="http://server/frame.png",
        session=session,
        clock=lambda: NOW + timedelta(seconds=2),
    )
    client.poll_once()
    client.poll_once()
    client.poll_once()
    assert len(display.base) == 2
    assert len(display.partial) == 1
    assert display.events == ["init", "clear", "fast"]


def test_transient_outage_retains_last_good_pixels():
    display = FakeDisplay()
    client = FrameClient(
        display,
        url="http://server/frame.png",
        session=FakeSession([frame_response()]),
        clock=lambda: NOW,
    )
    monotonic = MutableClock(100.0)
    diagnostic = OutageDiagnosticController(
        client, threshold_seconds=300, monotonic_clock=monotonic
    )

    client.poll_once()
    diagnostic.record_success()
    last_good = display.base[0].copy()
    monotonic.value = 101.0
    assert not diagnostic.record_failure(requests.Timeout("private endpoint"))
    monotonic.value = 399.9
    assert not diagnostic.record_failure(requests.Timeout("private endpoint"))

    assert len(display.base) == 1
    assert not display.partial
    assert display.base[0].tobytes() == last_good.tobytes()


def test_outage_threshold_transitions_to_local_diagnostic():
    display = FakeDisplay()
    client = FrameClient(display, url="http://server/frame.png")
    monotonic = MutableClock(10.0)
    diagnostic = OutageDiagnosticController(
        client,
        threshold_seconds=300,
        cadence_seconds=60,
        monotonic_clock=monotonic,
        local_clock=lambda: NOW,
    )

    assert not diagnostic.record_failure(requests.Timeout())
    monotonic.value = 309.9
    assert not diagnostic.record_failure(requests.Timeout())
    monotonic.value = 310.0
    assert diagnostic.record_failure(requests.Timeout())

    assert diagnostic.diagnostic_active
    assert len(display.base) == 1
    assert display.base[0].size == (120, 250)


def test_diagnostic_threshold_and_cadence_configuration_are_bounded(monkeypatch):
    monkeypatch.setenv("short", "1")
    monkeypatch.setenv("long", "999999")

    assert bounded_env_seconds("short", 300, minimum=30, maximum=86400) == 30
    assert bounded_env_seconds("long", 60, minimum=30, maximum=3600) == 3600
    assert bounded_env_seconds("missing", 60, minimum=30, maximum=3600) == 60


def test_outage_diagnostic_hard_limits_category_changes_to_low_cadence():
    display = FakeDisplay()
    client = FrameClient(display, url="http://server/frame.png")
    monotonic = MutableClock(0.0)
    diagnostic = OutageDiagnosticController(
        client,
        threshold_seconds=300,
        cadence_seconds=60,
        monotonic_clock=monotonic,
        local_clock=lambda: NOW,
    )

    diagnostic.record_failure(requests.Timeout())
    monotonic.value = 300.0
    assert diagnostic.record_failure(requests.Timeout())
    monotonic.value = 359.9
    assert not diagnostic.record_failure(requests.Timeout())
    assert len(display.base) + len(display.partial) == 1
    monotonic.value = 360.0
    assert diagnostic.record_failure(requests.Timeout())
    assert len(display.base) + len(display.partial) == 2
    monotonic.value = 361.0
    assert not diagnostic.record_failure(ValueError("frame is stale (301.0s old)"))
    monotonic.value = 420.0
    assert diagnostic.record_failure(ValueError("frame is stale (301.0s old)"))
    assert len(display.base) + len(display.partial) == 3


def test_clock_sync_change_is_coalesced_until_diagnostic_cadence():
    display = FakeDisplay()
    client = FrameClient(display, url="http://server/frame.png")
    monotonic = MutableClock(0.0)
    synchronized = MutableClock(False)
    diagnostic = OutageDiagnosticController(
        client,
        threshold_seconds=300,
        cadence_seconds=60,
        monotonic_clock=monotonic,
        local_clock=lambda: NOW,
        clock_synchronized=synchronized,
    )

    diagnostic.record_failure(requests.Timeout())
    monotonic.value = 300.0
    assert diagnostic.record_failure(requests.Timeout())
    synchronized.value = True
    monotonic.value = 301.0
    assert not diagnostic.record_failure(requests.Timeout())
    monotonic.value = 360.0
    assert diagnostic.record_failure(requests.Timeout())

    assert len(display.base) + len(display.partial) == 2


def test_clock_sync_marker_errors_are_safe_and_unsynchronized(monkeypatch):
    def fail_exists(_path):
        raise PermissionError("private path details")

    monkeypatch.setattr("display_client.Path.exists", fail_exists)

    assert not clock_sync_marker_present("/run/systemd/timesync/synchronized")
    assert clock_sync_marker_present("")


@pytest.mark.parametrize(
    "exc, expected",
    [
        (requests.Timeout("http://secret-host/token"), "timeout"),
        (
            requests.ConnectionError(socket.gaierror(-2, "private.example")),
            "dns",
        ),
        (requests.ConnectionError("192.168.1.2 refused"), "connection"),
        (ValueError("frame is stale (999s old)"), "stale"),
        (ValueError("frame timestamp is too far in the future"), "future-timestamp"),
        (ValueError("token=do-not-display"), "protocol"),
    ],
)
def test_poll_errors_are_reduced_to_sanitized_categories(exc, expected):
    category = categorize_poll_error(exc)
    view = build_diagnostic_view(
        category,
        local_now=NOW,
        seconds_since_success=900,
        clock_synchronized=True,
    )

    assert category == expected
    rendered_text = " ".join(view.lines)
    assert "secret-host" not in rendered_text
    assert "192.168" not in rendered_text
    assert "do-not-display" not in rendered_text


def test_http_auth_error_has_stable_sanitized_category():
    response = requests.Response()
    response.status_code = 403
    error = requests.HTTPError("403 for private URL", response=response)

    assert categorize_poll_error(error) == "auth"


def test_diagnostic_view_includes_local_time_and_last_success_age():
    view = build_diagnostic_view(
        "timeout",
        local_now=NOW,
        seconds_since_success=900,
        clock_synchronized=True,
    )

    assert view.lines[1] == "Local: 2026-07-15 12:00 UTC"
    assert view.lines[2] == "Last frame: 15m ago"


def test_verified_not_modified_response_restores_frame_after_diagnostic():
    display = FakeDisplay()
    not_modified = FakeResponse(
        status=304,
        headers={"X-Display-Published-At": NOW.isoformat()},
    )
    client = FrameClient(
        display,
        url="http://server/frame.png",
        session=FakeSession([frame_response(), not_modified]),
        clock=lambda: NOW,
    )
    monotonic = MutableClock(0.0)
    diagnostic = OutageDiagnosticController(
        client,
        threshold_seconds=30,
        monotonic_clock=monotonic,
        local_clock=lambda: NOW,
    )

    client.poll_once()
    diagnostic.record_success()
    verified_pixels = display.base[0].tobytes()
    monotonic.value = 1.0
    diagnostic.record_failure(requests.Timeout())
    monotonic.value = 31.0
    assert diagnostic.record_failure(requests.Timeout())
    assert client.last_sequence == 1
    assert client.etag == '"1-etag"'
    assert client.poll_once().status == "restored"

    assert not client.diagnostic_displayed
    assert display.partial[-1].tobytes() == verified_pixels


def test_wall_clock_jump_does_not_accelerate_threshold_and_unsynced_is_explicit():
    display = FakeDisplay()
    client = FrameClient(display, url="http://server/frame.png")
    monotonic = MutableClock(0.0)
    wall = MutableClock(NOW)
    diagnostic = OutageDiagnosticController(
        client,
        threshold_seconds=300,
        monotonic_clock=monotonic,
        local_clock=wall,
        clock_synchronized=lambda: False,
    )

    diagnostic.record_failure(ValueError("frame timestamp is too far in the future"))
    wall.value = NOW + timedelta(days=3650)
    monotonic.value = 1.0
    assert not diagnostic.record_failure(
        ValueError("frame timestamp is too far in the future")
    )
    monotonic.value = 300.0
    assert diagnostic.record_failure(
        ValueError("frame timestamp is too far in the future")
    )
    view = build_diagnostic_view(
        "future-timestamp",
        local_now=wall.value,
        seconds_since_success=None,
        clock_synchronized=False,
    )

    assert "not synchronized" in view.lines[1]
    assert "2036" not in " ".join(view.lines)


def test_monotonic_rollback_restarts_outage_threshold_safely():
    display = FakeDisplay()
    client = FrameClient(display, url="http://server/frame.png")
    monotonic = MutableClock(1000.0)
    diagnostic = OutageDiagnosticController(
        client, threshold_seconds=300, monotonic_clock=monotonic
    )

    diagnostic.record_failure(requests.Timeout())
    monotonic.value = 900.0
    assert not diagnostic.record_failure(requests.Timeout())
    monotonic.value = 1199.9
    assert not diagnostic.record_failure(requests.Timeout())
    monotonic.value = 1200.0
    assert diagnostic.record_failure(requests.Timeout())


def test_shutdown_prevents_later_diagnostic_writes():
    display = FakeDisplay()
    client = FrameClient(display, url="http://server/frame.png")
    monotonic = MutableClock(0.0)
    diagnostic = OutageDiagnosticController(
        client, threshold_seconds=30, monotonic_clock=monotonic
    )

    diagnostic.record_failure(requests.Timeout())
    diagnostic.shutdown()
    monotonic.value = 30.0

    assert not diagnostic.record_failure(requests.Timeout())
    assert not display.base
    assert not display.partial


def test_health_reporter_is_atomic_tmpfs_contract_and_deduplicates(tmp_path):
    path = tmp_path / "client-health.json"
    reporter = HealthReporter(path)
    health = ClientHealth(
        schema_version=1,
        role="display-client",
        boot_id=reporter.boot_id,
        pid=123,
        state="healthy",
        sequence=4,
        etag='"4-test"',
        last_attempt_at=NOW.isoformat(),
        last_success_at=NOW.isoformat(),
        last_error_at=None,
        error=None,
        frame_source_created_at=NOW.isoformat(),
    )
    reporter.write(health)
    first_mtime = path.stat().st_mtime_ns
    reporter.write(health)
    assert path.stat().st_mtime_ns == first_mtime
    assert json.loads(path.read_text())["role"] == "display-client"
    assert not list(tmp_path.glob("*.tmp"))


def test_systemd_notifier_writes_to_notify_socket():
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        path = f"{directory}/notify.sock"
        receiver = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        receiver.bind(path)
        receiver.settimeout(1)
        try:
            assert SystemdNotifier(path).notify("READY=1", "WATCHDOG=1")
            assert receiver.recv(1024) == b"READY=1\nWATCHDOG=1"
        finally:
            receiver.close()
