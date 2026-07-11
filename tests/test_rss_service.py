from datetime import timezone

from rss_service import FeedSource, RSSWatcher, configured_sources, env_int, parse_feed

RSS = b"""<?xml version="1.0"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Alice / Nitter</title>
    <image><url>/pic/avatar.jpg</url></image>
    <item>
      <title>Hello &amp; welcome to &lt;b&gt;the feed&lt;/b&gt;</title>
      <dc:creator>Alice Example</dc:creator>
      <link>https://nitter.test/alice/status/1</link>
      <guid>tweet-1</guid>
      <pubDate>Sat, 11 Jul 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


class Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class Session:
    def __init__(self, contents):
        self.contents = list(contents)

    def get(self, url, timeout):
        return Response(self.contents.pop(0))


def test_nitter_feed_parses_identity_text_and_avatar():
    source = FeedSource("https://nitter.test/alice/rss", "nitter", handle="@alice")

    entry = parse_feed(RSS, source)[0]

    assert entry.kind == "nitter"
    assert entry.publication == "Alice / Nitter"
    assert entry.author == "Alice Example"
    assert entry.handle == "@alice"
    assert entry.title == "Hello & welcome to the feed"
    assert entry.avatar_url == "https://nitter.test/pic/avatar.jpg"
    assert entry.published.tzinfo == timezone.utc


def test_feed_parses_category_metadata():
    content = RSS.replace(
        b"<guid>tweet-1</guid>",
        b"<guid>tweet-1</guid><category>Sport</category>",
    )

    entry = parse_feed(content, FeedSource("https://news.test/rss"))[0]

    assert entry.categories == ("Sport",)


def test_configured_sources_builds_nitter_and_arbitrary_feeds(monkeypatch):
    monkeypatch.setenv("rss_nitter_base_url", "http://nitter.local/")
    monkeypatch.setenv("rss_nitter_users", "alice, @bob")
    monkeypatch.setenv("rss_feed_urls", "https://example.com/rss, https://x.test/atom")

    sources = configured_sources()

    assert [source.url for source in sources] == [
        "http://nitter.local/alice/rss",
        "http://nitter.local/bob/rss",
        "https://example.com/rss",
        "https://x.test/atom",
    ]
    assert [source.kind for source in sources] == ["nitter", "nitter", "rss", "rss"]


def test_configured_sources_supports_nitter_with_replies_path(monkeypatch):
    monkeypatch.setenv("rss_nitter_base_url", "http://nitter.local")
    monkeypatch.setenv("rss_nitter_users", "alice")
    monkeypatch.setenv("rss_nitter_feed_path", "/{handle}/with_replies/rss")
    monkeypatch.delenv("rss_feed_urls", raising=False)

    assert configured_sources()[0].url == ("http://nitter.local/alice/with_replies/rss")


def test_invalid_integer_environment_uses_default(monkeypatch):
    monkeypatch.setenv("rss_watch_timeout", "not-a-number")

    assert env_int("rss_watch_timeout", 10) == 10


def test_non_object_state_file_recovers_as_empty(monkeypatch, tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text("null", encoding="utf-8")
    monkeypatch.setenv("rss_watch_state_file", str(state_path))

    watcher = RSSWatcher([], session=Session([]))

    assert watcher._seen == {}


def test_first_poll_baselines_and_later_poll_returns_only_new_entry(
    monkeypatch, tmp_path
):
    second = RSS.replace(
        b"<item>",
        b"<item><title>Second post</title><guid>tweet-2</guid></item><item>",
        1,
    )
    monkeypatch.setenv("rss_watch_enabled", "true")
    monkeypatch.setenv("rss_watch_state_file", str(tmp_path / "state.json"))
    watcher = RSSWatcher(
        [FeedSource("https://nitter.test/alice/rss", "nitter")],
        session=Session([RSS, second]),
    )

    assert watcher.poll() == []
    new_entries = watcher.poll()

    assert [entry.title for entry in new_entries] == ["Second post"]
    assert (tmp_path / "state.json").exists()
