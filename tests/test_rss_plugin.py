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


def test_invalid_integer_settings_do_not_crash_startup(monkeypatch):
    monkeypatch.setenv("rss_watch_poll_seconds", "")
    monkeypatch.setenv("rss_watch_display_seconds", "invalid")
    monkeypatch.setenv("rss_watch_priority", "invalid")
    monkeypatch.setenv("rss_watch_max_queue", "invalid")
    watcher = SimpleNamespace(enabled=True, sources=[object()])

    plugin = RSSPlugin(object(), ScreenArbiter(), threading.Lock(), watcher=watcher)

    assert plugin.poll_seconds == 60
    assert plugin.duration == 60
    assert plugin.priority == 30
    assert plugin.max_queue == 10


def test_run_does_not_tick_after_stop_during_poll(monkeypatch):
    watcher = SimpleNamespace(enabled=True, sources=[object()])
    plugin = RSSPlugin(object(), ScreenArbiter(), threading.Lock(), watcher=watcher)
    ticks = []

    def poll():
        plugin._stop_event.set()
        return []

    watcher.poll = poll
    monkeypatch.setattr(plugin, "tick", lambda now: ticks.append(now))

    plugin._run()

    assert ticks == []


def test_oversized_avatar_is_not_buffered_for_render(monkeypatch):
    rendered = []

    class AvatarResponse:
        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"x" * 300_000
            yield b"x" * 300_000

    class AvatarSession:
        def get(self, url, timeout, stream):
            assert stream is True
            return AvatarResponse()

    monkeypatch.setattr(
        "rss_plugin.draw_feed_entry",
        lambda epd, entry, **kwargs: rendered.append(kwargs["avatar_bytes"]),
    )
    watcher = SimpleNamespace(
        enabled=True,
        sources=[object()],
        session=AvatarSession(),
        timeout=1,
    )
    plugin = RSSPlugin(object(), ScreenArbiter(), threading.Lock(), watcher=watcher)
    entry = _entry()
    entry = type(entry)(**{**entry.__dict__, "avatar_url": "https://example.test/a"})
    plugin.add_entries([entry])

    plugin.tick()

    assert rendered == [None]
