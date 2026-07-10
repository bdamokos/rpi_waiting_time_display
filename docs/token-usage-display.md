---
layout: default
title: Token usage display
---

# Token usage display

The optional token mode rotates between a month-to-date usage-value chart and
remaining-capacity bars for a five-hour and weekly window. It is disabled by
default and does not change existing installations until
`token_usage_enabled=true` is configured.

## Scheduling

`display_schedule` is a comma-separated list of
`mode@HH:MM-HH:MM` entries. The first matching entry wins, and ranges may cross
midnight. For example:

```dotenv
display_schedule=transit@06:00-10:00,token@10:00-22:00,weather@22:00-06:00
token_usage_view_duration=300
token_usage_views=month,limits
token_usage_fallback_mode=transit
```

Supported modes are `auto`, `transit`, `weather`, and `token`. When token data
is unavailable, `token_usage_fallback_mode` is used. The last good response is
cached for `token_usage_max_stale_seconds`; stale views are visibly marked.

## Data sources

The display can fetch a snapshot over HTTP or read it from a local file:

```dotenv
token_usage_source=http
token_usage_url=http://usage-server.local:8765/snapshot
token_usage_auth_token=replace-with-a-random-secret
```

For a file source, set `token_usage_source=file` and `token_usage_file` instead.
Never commit the real URL, bearer token, account identifiers, credentials, or
personal usage data.

The repository includes `tools/token_usage_server.py`, a small authenticated
bridge for machines that already have the `codexbar` CLI and Codex credentials:

```bash
TOKEN_USAGE_SERVER_TOKEN_FILE=~/.config/token-display/token \
  python tools/token_usage_server.py --host 0.0.0.0 --port 8765
```

Listening beyond loopback is refused unless a bearer token is configured. The
bridge returns only the display fields below; account email, account ID, OAuth
tokens, session names, and project paths are not exposed.

## Snapshot schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-01-15T12:00:00+01:00",
  "currency": "USD",
  "limits": {
    "primary": {"used_percent": 25, "resets_at": "2026-01-15T16:00:00Z"},
    "secondary": {"used_percent": 40, "resets_at": "2026-01-20T09:00:00Z"}
  },
  "month_to_date": {"cost_usd": 123.45, "total_tokens": 234567890},
  "daily": [
    {"date": "2026-01-15", "cost_usd": 12.34, "total_tokens": 23456789}
  ]
}
```

The cost shown from local Codex logs is an estimated API-price equivalent. It
is not an invoice or the amount charged for a ChatGPT subscription.
