"""Generate deterministic README screenshots with the real display renderers."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calendar_display import draw_calendar_agenda, draw_upcoming_event
from calendar_service import CalendarEvent
from display_adapter import MockDisplay
from rss_display import draw_feed_entry
from rss_service import FeedEntry
from token_display import draw_month_usage, draw_usage_limits
from token_usage import TokenUsageSnapshot


OUTPUT = ROOT / "docs" / "images"


def save(name: str) -> None:
    shutil.move(ROOT / "debug_output.png", OUTPUT / name)


def main() -> None:
    display = MockDisplay()
    local_tz = ZoneInfo("Europe/Brussels")
    now = datetime(2026, 7, 11, 9, 20, tzinfo=local_tz)

    review = CalendarEvent(
        uid="weekly-review",
        summary="Weekly product review and planning",
        start=now + timedelta(minutes=10),
        end=now + timedelta(minutes=55),
        location="Meeting room 12",
    )
    draw_upcoming_event(display, review, now, set_base_image=True)
    save("calendar_event_mock.png")

    agenda = [
        review,
        CalendarEvent(
            uid="lunch",
            summary="Lunch with Sam",
            start=now + timedelta(hours=3, minutes=10),
            end=now + timedelta(hours=4),
        ),
        CalendarEvent(
            uid="train",
            summary="Train to Brussels",
            start=now + timedelta(days=1, hours=5),
            end=now + timedelta(days=1, hours=6),
        ),
    ]
    draw_calendar_agenda(display, agenda, now, set_base_image=True)
    save("calendar_agenda_mock.png")

    tweet = FeedEntry(
        key="nitter-demo",
        source_url="https://example.test/alice/rss",
        kind="nitter",
        publication="Alice Example",
        title="The new e-paper calendar and feed displays are now ready to try.",
        author="Alice Example",
        handle="@alice",
        published=datetime(2026, 7, 11, 8, 42, tzinfo=timezone.utc),
    )
    draw_feed_entry(display, tweet, set_base_image=True)
    save("rss_nitter_mock.png")

    article = FeedEntry(
        key="rss-demo",
        source_url="https://example.test/feed.xml",
        kind="rss",
        publication="Transit Updates",
        title="Weekend service changes begin this evening across the city",
        author="Operations desk",
        published=datetime(2026, 7, 11, 9, 5, tzinfo=timezone.utc),
    )
    draw_feed_entry(display, article, set_base_image=True)
    save("rss_article_mock.png")

    snapshot = TokenUsageSnapshot.from_dict(
        {
            "generated_at": now.isoformat(),
            "active": True,
            "currency": "USD",
            "limits": {
                "resets_available": 2,
                "primary": {"used_percent": 18, "resets_at": "2026-07-11T13:00:00Z"},
                "secondary": {"used_percent": 45, "resets_at": "2026-07-14T15:00:00Z"},
            },
            "month_to_date": {"cost_usd": 124, "total_tokens": 234_000_000},
            "daily": [
                {"date": f"2026-07-{day:02d}", "cost_usd": cost, "total_tokens": 0}
                for day, cost in enumerate(
                    (8, 13, 9, 18, 14, 22, 17, 23, 20, 31, 27), 1
                )
            ],
        }
    )
    draw_month_usage(display, snapshot, set_base_image=True)
    save("codex_month_usage_mock.png")
    draw_usage_limits(display, snapshot, set_base_image=True)
    save("codex_capacity_mock.png")


if __name__ == "__main__":
    main()
