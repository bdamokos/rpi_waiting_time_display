import io
from datetime import datetime, timezone

import pytest
from PIL import Image

from display_adapter import MockDisplay
from rss_display import draw_feed_entry
from rss_service import FeedEntry


def test_tweet_and_generic_cards_render(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    epd = MockDisplay()
    for kind in ("nitter", "rss"):
        entry = FeedEntry(
            key=kind,
            source_url="https://example.test/feed",
            kind=kind,
            publication="Example Publication",
            title="A sufficiently long post title that exercises compact wrapping on the display",
            author="Alice Example",
            handle="@alice",
            published=datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc),
        )
        draw_feed_entry(epd, entry, set_base_image=True)
        assert (tmp_path / "debug_output.png").stat().st_size > 0


@pytest.mark.parametrize("display_type", ["bw", "bwr", "bwry"])
@pytest.mark.parametrize("image_format", ["JPEG", "PNG", "GIF"])
def test_tweet_avatar_is_decoded_and_fitted(
    monkeypatch, tmp_path, display_type, image_format
):
    monkeypatch.setenv("mock_display_type", display_type)
    monkeypatch.setattr("rss_display.DISPLAY_SCREEN_ROTATION", 90)
    monkeypatch.chdir(tmp_path)
    epd = MockDisplay()
    frames = []
    monkeypatch.setattr(epd, "getbuffer", lambda image: image)
    monkeypatch.setattr(epd, "displayPartial", frames.append)
    entry = FeedEntry(
        key="avatar",
        source_url="https://example.test/feed",
        kind="nitter",
        publication="Example",
        title="Post with an avatar",
        author="Alice",
    )
    avatar = io.BytesIO()
    Image.new("RGB", (320, 160), "black").save(avatar, format=image_format)

    draw_feed_entry(epd, entry, avatar_bytes=avatar.getvalue())

    assert len(frames) == 1
    landscape = frames[0].rotate(-90, expand=True).convert("L")
    assert landscape.size == (250, 120)
    assert landscape.crop((7, 30, 45, 68)).getextrema() == (0, 0)


@pytest.mark.parametrize("avatar_bytes", [b"not an image", b"\x89PNG\r\n\x1a\n"])
def test_invalid_avatar_keeps_the_text_only_card(monkeypatch, tmp_path, avatar_bytes):
    monkeypatch.chdir(tmp_path)
    epd = MockDisplay()
    frames = []
    monkeypatch.setattr(epd, "getbuffer", lambda image: image)
    monkeypatch.setattr(epd, "displayPartial", frames.append)
    entry = FeedEntry(
        key="invalid-avatar",
        source_url="https://example.test/feed",
        kind="nitter",
        publication="Example",
        title="Post without a usable avatar",
        author="Alice",
    )

    draw_feed_entry(epd, entry)
    draw_feed_entry(epd, entry, avatar_bytes=avatar_bytes)

    assert len(frames) == 2
    assert frames[0].mode == frames[1].mode
    assert frames[0].size == frames[1].size
    assert frames[0].tobytes() == frames[1].tobytes()
