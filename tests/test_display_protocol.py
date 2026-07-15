import hashlib
import json
from datetime import datetime, timezone

import pytest
from PIL import Image

from display_protocol import FramePublisher, validate_frame_bytes
from publication_display import PublicationDisplay

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def test_publisher_atomically_records_exact_frame_and_continues_sequence(tmp_path):
    publisher = FramePublisher(tmp_path, clock=lambda: NOW)
    snapshot = publisher.publish(Image.new("1", (250, 120), 1))

    assert snapshot.metadata.sequence == 1
    assert snapshot.metadata.published_at == NOW.isoformat()
    assert validate_frame_bytes((tmp_path / "latest.png").read_bytes()).size == (
        250,
        120,
    )
    assert (
        json.loads((tmp_path / "latest.json").read_text())["sha256"]
        == hashlib.sha256(snapshot.content).hexdigest()
    )
    assert not list(tmp_path.glob("*.tmp"))

    restarted = FramePublisher(tmp_path, clock=lambda: NOW)
    assert restarted.publish(Image.new("1", (250, 120), 0)).metadata.sequence == 2


def test_publisher_refuses_wrong_dimensions_and_invalid_png(tmp_path):
    with pytest.raises(ValueError, match="published frame"):
        FramePublisher(tmp_path).publish(Image.new("1", (120, 250), 1))
    with pytest.raises(ValueError, match="not a PNG"):
        validate_frame_bytes(b"not-an-image")


def test_publication_display_rotates_renderer_buffer_to_250x120(tmp_path, monkeypatch):
    monkeypatch.setenv("screen_rotation", "90")
    publisher = FramePublisher(tmp_path, clock=lambda: NOW)
    display = PublicationDisplay(publisher)
    renderer_buffer = Image.new("1", (120, 250), 1)
    renderer_buffer.putpixel((0, 0), 0)

    display.displayPartial(display.getbuffer(renderer_buffer))

    frame = validate_frame_bytes(publisher.snapshot().content)
    assert frame.size == (250, 120)
    assert display.height == 250
    assert display.width == 120
