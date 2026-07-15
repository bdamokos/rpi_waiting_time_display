import hashlib
import io
import json
import socket
import tempfile
from datetime import datetime, timedelta, timezone

import pytest
import requests
from PIL import Image

from display_client import ClientHealth, FrameClient, HealthReporter, SystemdNotifier

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
