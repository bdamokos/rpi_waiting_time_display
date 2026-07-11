# RSS watch display

The optional RSS watcher polls standard RSS or Atom feeds and briefly displays
new entries through the shared screen arbiter. It supports two layouts:

- Nitter feeds show the author, `@handle`, tweet text, and the feed avatar when
  one is advertised by the channel.
- Other feeds show the publication and post title, with an author when present.

The 250x120 layout deliberately omits URLs and article summaries. The feed URL
remains the source of truth, while the display is a readable notification.

## Configuration

```dotenv
rss_watch_enabled=true
rss_nitter_base_url=http://your-nitter-instance
rss_nitter_users=account_one,account_two
rss_feed_urls=https://example.org/feed.xml,https://example.net/atom.xml
```

The first successful poll records a baseline and does not display old entries.
State is retained in `cache/rss-watch-state.json`, so restarts do not replay
posts. Set `rss_watch_show_existing=true` only when testing the layout.

Each entry claims the screen for `rss_watch_display_seconds` (60 by default) at
priority `rss_watch_priority` (30 by default). A higher-priority arbiter claim
can override it. Up to `rss_watch_max_queue` entries are shown in chronological
order; older excess notifications are discarded.

Feed requests use `rss_watch_timeout`. Feed credentials and private hostnames
belong only in the ignored `.env`, never in tracked configuration.
