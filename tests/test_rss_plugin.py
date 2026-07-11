import threading
from types import SimpleNamespace

from rss_plugin import RSSPlugin
from rss_service import FeedEntry
from screen_arbiter import ScreenArbiter


def _entry(key="one"):
    return FeedEntry(
        key=key,
        source_url="https://example.test/rss",
        kind="rss",
        publication="Example",
        title=f"Post {key}",
    )


def _plugin(monkeypatch, rendered):
    monkeypatch.setenv("rss_watch_display_seconds", "60")
    monkeypatch.setenv("rss_watch_priority", "30")
    monkeypatch.setattr(
        "rss_plugin.draw_feed_entry",
        lambda epd, entry, **kwargs: rendered.append(entry.key),
    )
    watcher = SimpleNamespace(enabled=True, sources=[object()], session=None, timeout=1)

    def clock():
        return 100

    return RSSPlugin(
        object(), ScreenArbiter(clock), threading.Lock(), watcher=watcher, clock=clock
    )


def test_new_entry_claims_screen_for_configured_duration(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    plugin.add_entries([_entry()])

    plugin.tick(100)

    claim = plugin.arbiter.claim_for(plugin.OWNER)
    assert claim.priority == 30
    assert claim.expires_at == 160
    assert rendered == ["one"]

    plugin.tick(160)
    assert plugin.arbiter.active_owner() is None


def test_higher_priority_owner_overrides_rss(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    plugin.arbiter.claim("flight", 50, 30)
    plugin.add_entries([_entry()])

    plugin.tick(100)

    assert plugin.arbiter.active_owner() == "flight"
    assert rendered == []


def test_queued_entries_render_in_order(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    plugin.add_entries([_entry("one"), _entry("two")])

    plugin.tick(100)
    plugin.tick(160)

    assert rendered == ["one", "two"]
