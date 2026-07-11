# Breaking-news display

The optional breaking-news module watches explicitly configured RSS/Atom feeds
and shows a high-contrast headline card for about four minutes. It does not
scrape news sites. It is disabled unless both `breaking_news_enabled=true` and
at least one valid source are present.

## Private source configuration

Keep source URLs, API keys, and customer-specific feed identifiers in the
ignored `breaking-news-feeds.json` file (or point `breaking_news_config_file` at
another private path):

```json
[
  {
    "url": "https://feeds.bbci.co.uk/news/rss.xml",
    "label": "BBC News",
    "match": "keywords"
  },
  {
    "url": "https://licensed-provider.example/breaking.xml",
    "label": "Licensed wire",
    "match": "all",
    "headers": {"Authorization": "Bearer keep-this-out-of-git"}
  }
]
```

`match: "keywords"` only announces new headlines containing the source's
`keywords` list, which defaults to `breaking`, `breaking news`, `urgent`,
`news alert`, and `developing`. Override it per source when the publisher uses
different labels. Use `match: "all"` only for a feed whose publisher defines
every item as breaking; using it on a general news feed creates false alerts.

BBC publishes an official headline RSS feed at the URL shown above. AP offers
authenticated feeds and RSS products to entitled Media API customers; use only
the URLs and credentials supplied under your AP plan. This module does not ship
AP, CNN, or Reuters URLs: no unauthenticated official breaking RSS endpoint is
assumed for them. A publisher-provided or licensed RSS/Atom URL can be added
without a code change when its terms allow this use.

## New-item detection and failure behavior

The first successful poll of each source establishes a baseline and displays
nothing. Later items must be unseen, recent, match the source rule, and have a
headline not already announced by another source. Prefixes and punctuation are
normalized for cross-feed deduplication. Items older than
`breaking_news_max_age_seconds` are ignored, preventing stale feed reorderings
from becoming alerts.

State is written atomically to `cache/breaking-news-state.json`. Per-feed IDs,
cross-feed fingerprints, and the on-screen queue are bounded by configuration.
A missing or corrupt state file safely returns to baseline behavior. Failed
sources are logged without blocking healthy sources or the normal display.

Polling defaults to five minutes and cannot be configured below 60 seconds.
ETag and Last-Modified validators are retained and sent on later requests, so
publishers can answer with `304 Not Modified`. Use longer intervals if required
by a feed's terms. Requests carry a configurable user agent and feed bodies are
limited to 1 MiB by default. Failure logs identify only the source hostname, so
credentials embedded in private paths or query strings are not printed.

## Display arbitration

Each queued headline gets a 240-second, non-exclusive claim at priority `70`.
It normally interrupts the base, RSS, flight, and ISS screens, while a higher
priority or exclusive claim can override it. The four-minute timer is
wall-clock based and continues during an override, so a delayed alert cannot
take over the display indefinitely afterward. At most three alerts are queued
by default; the oldest excess alert is discarded.
