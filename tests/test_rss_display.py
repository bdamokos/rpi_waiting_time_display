from datetime import datetime, timezone

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
