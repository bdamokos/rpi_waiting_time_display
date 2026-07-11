import threading
from types import SimpleNamespace

from breaking_news_plugin import BreakingNewsPlugin
from rss_service import FeedEntry
from screen_arbiter import ScreenArbiter


def _entry(key="one"):
    return FeedEntry(
        key, "https://news.test/rss", "breaking", "News", f"Headline {key}"
    )


def _plugin(monkeypatch, rendered):
    monkeypatch.setenv("breaking_news_display_seconds", "240")
    monkeypatch.setenv("breaking_news_priority", "70")

    def render(epd, entry, **kwargs):
        rendered.append(entry.key)

    monkeypatch.setattr(
        "breaking_news_plugin.draw_breaking_news",
        render,
    )
    watcher = SimpleNamespace(enabled=True, sources=[object()])

    def clock():
        return 100

    return BreakingNewsPlugin(
        object(),
        ScreenArbiter(clock),
        threading.Lock(),
        watcher=watcher,
        clock=clock,
    )


def test_alert_claims_screen_for_four_minutes(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    plugin.add_entries([_entry()])

    plugin.tick(100)

    claim = plugin.arbiter.claim_for(plugin.OWNER)
    assert claim.priority == 70
    assert claim.expires_at == 340
    assert claim.exclusive is False
    assert rendered == ["one"]


def test_higher_priority_override_wins_and_alert_expires_in_wall_clock_time(
    monkeypatch,
):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    plugin.arbiter.claim("critical", 100, 300)
    plugin.add_entries([_entry()])

    plugin.tick(100)
    plugin.tick(340)

    assert rendered == []
    assert plugin.arbiter.active_owner() == "critical"
    assert not plugin._queue


def test_queue_is_bounded(monkeypatch):
    rendered = []
    monkeypatch.setenv("breaking_news_max_queue", "2")
    plugin = _plugin(monkeypatch, rendered)

    plugin.add_entries([_entry("one"), _entry("two"), _entry("three")])

    assert [entry.key for entry in plugin._queue] == ["two", "three"]
