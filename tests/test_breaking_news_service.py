# flake8: noqa: E501
import json
from datetime import datetime, timezone

from breaking_news_service import (
    BreakingNewsWatcher,
    BreakingSource,
    configured_breaking_sources,
    headline_fingerprint,
)


def _rss(*items):
    body = "".join(
        f"<item><title>{title}</title><guid>{guid}</guid>"
        f"<pubDate>Sat, 11 Jul 2026 10:00:00 GMT</pubDate></item>"
        for guid, title in items
    )
    return (f"<rss><channel><title>News Wire</title>{body}</channel></rss>").encode()


class Response:
    def __init__(self, content=b"", status=200, headers=None):
        self.content = content
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("request failed")

    def iter_content(self, chunk_size):
        yield self.content

    def close(self):
        return None


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, timeout, headers, stream):
        self.requests.append((url, timeout, headers, stream))
        return self.responses.pop(0)


def _watcher(monkeypatch, tmp_path, sources, responses):
    monkeypatch.setenv("breaking_news_enabled", "true")
    monkeypatch.setenv("breaking_news_state_file", str(tmp_path / "state.json"))
    return BreakingNewsWatcher(
        sources,
        session=Session(responses),
        now=lambda: datetime(2026, 7, 11, 10, 5, tzinfo=timezone.utc),
    )


def test_private_config_supports_rules_and_headers(monkeypatch, tmp_path):
    path = tmp_path / "feeds.json"
    path.write_text(
        json.dumps(
            [
                {
                    "url": "https://wire.test/feed",
                    "label": "Wire",
                    "match": "all",
                    "headers": {"Authorization": "Bearer secret"},
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("breaking_news_config_file", str(path))

    sources = configured_breaking_sources()

    assert sources == [
        BreakingSource(
            "https://wire.test/feed",
            "Wire",
            "all",
            headers=(("Authorization", "Bearer secret"),),
        )
    ]


def test_private_config_rejects_null_url_and_defaults_null_options(
    monkeypatch, tmp_path
):
    path = tmp_path / "feeds.json"
    path.write_text(
        json.dumps(
            [
                {"url": None, "label": None},
                {
                    "url": "https://wire.test/feed",
                    "label": None,
                    "match": None,
                    "keywords": None,
                    "headers": None,
                },
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("breaking_news_config_file", str(path))

    assert configured_breaking_sources() == [BreakingSource("https://wire.test/feed")]


def test_keyword_normalization_uses_unicode_case_folding(monkeypatch, tmp_path):
    path = tmp_path / "feeds.json"
    path.write_text(
        json.dumps(
            [
                {
                    "url": "https://wire.test/feed",
                    "keywords": ["STRAẞE"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("breaking_news_config_file", str(path))

    assert configured_breaking_sources()[0].keywords == ("strasse",)


def test_first_poll_baselines_then_only_new_matching_headline_is_returned(
    monkeypatch, tmp_path
):
    source = BreakingSource("https://news.test/rss", label="News")
    watcher = _watcher(
        monkeypatch,
        tmp_path,
        [source],
        [
            Response(_rss(("1", "Breaking: first headline"))),
            Response(
                _rss(
                    ("3", "Routine update"),
                    ("2", "Breaking: second headline"),
                    ("1", "Breaking: first headline"),
                )
            ),
        ],
    )

    assert watcher.poll() == []
    result = watcher.poll()

    assert [entry.title for entry in result] == ["Breaking: second headline"]


def test_cross_source_headline_dedup_ignores_breaking_prefix_and_punctuation(
    monkeypatch, tmp_path
):
    sources = [
        BreakingSource("https://one.test/rss", match="all"),
        BreakingSource("https://two.test/rss", match="all"),
    ]
    watcher = _watcher(
        monkeypatch,
        tmp_path,
        sources,
        [
            Response(_rss(("1", "Old one"))),
            Response(_rss(("1", "Old two"))),
            Response(_rss(("2", "BREAKING: Major event!"), ("1", "Old one"))),
            Response(_rss(("2", "Major event"), ("1", "Old two"))),
        ],
    )
    watcher.poll()

    result = watcher.poll()

    assert len(result) == 1
    first = headline_fingerprint("BREAKING: Major event!")
    second = headline_fingerprint("Major event")
    assert first == second


def test_conditional_get_validators_and_304(monkeypatch, tmp_path):
    source = BreakingSource("https://news.test/rss")
    watcher = _watcher(
        monkeypatch,
        tmp_path,
        [source],
        [
            Response(
                _rss(("1", "Old")),
                headers={"ETag": '"v1"', "Last-Modified": "yesterday"},
            ),
            Response(status=304),
        ],
    )

    watcher.poll()
    assert watcher.poll() == []
    headers = watcher.session.requests[1][2]
    assert headers["If-None-Match"] == '"v1"'
    assert headers["If-Modified-Since"] == "yesterday"
    assert headers["User-Agent"].startswith("rpi-waiting-time-display/")
    assert watcher.session.requests[1][3] is True


def test_oversized_feed_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("breaking_news_max_feed_bytes", "1024")
    source = BreakingSource("https://news.test/private?token=secret")
    watcher = _watcher(monkeypatch, tmp_path, [source], [Response(b"x" * 1025)])

    assert watcher.poll() == []
    assert not (tmp_path / "state.json").exists()
