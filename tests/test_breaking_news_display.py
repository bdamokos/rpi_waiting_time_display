from datetime import datetime, timezone

from breaking_news_display import draw_breaking_news
from display_adapter import MockDisplay
from rss_service import FeedEntry


def test_breaking_news_card_renders_on_213_inch_canvas(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    entry = FeedEntry(
        key="breaking-1",
        source_url="https://example.test/feed",
        kind="breaking",
        publication="Example News Wire",
        title=(
            "Breaking: a sufficiently long headline wraps cleanly across "
            "the compact e-paper display"
        ),
        published=datetime(2026, 7, 11, 10, 0, tzinfo=timezone.utc),
    )

    draw_breaking_news(MockDisplay(), entry, set_base_image=True)

    assert (tmp_path / "debug_output.png").stat().st_size > 0
