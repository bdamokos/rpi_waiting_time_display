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

`display_schedule` is a comma-separated list of `mode@HH:MM-HH:MM` entries.
To limit an entry by day, use `mode@DAYS@HH:MM-HH:MM`. The first matching entry
wins, and ranges may cross midnight. `DAYS` may be `daily`, `weekdays`,
`weekends`, one day (`mon`), an inclusive range (`mon-fri`), or a `+`-joined
combination (`mon+wed+fri`). Day matching uses the device's local timezone.

This example keeps Codex information visible throughout the weekend, preserves
transit on weekday mornings, shows Codex only while it is active during weekday
working hours, and shows weather on weekday nights:

```dotenv
display_schedule=token-always@weekends@00:00-00:00,transit@weekdays@06:00-10:00,token@weekdays@10:00-22:00,weather@weekdays@22:00-06:00
token_usage_view_duration=300
token_usage_views=month,limits
token_usage_fallback_mode=transit
```

Supported modes are `auto`, `transit`, `weather`, `token`, and `token-always`.
`token` is shown only while the source reports recent Codex activity;
`token-always` ignores activity but still requires a fresh snapshot. When token
data is unavailable, `token_usage_fallback_mode` is used. The last good response
is cached for `token_usage_max_stale_seconds`; stale data never keeps an active
or always-on token window visible.

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

By default the example bridge reports Codex as active when a `.json` or
`.jsonl` file below `$CODEX_HOME/sessions` (or `~/.codex/sessions`) was modified
in the last five minutes. Use `--activity-path` (repeatable) for another session
location and `--activity-window-seconds` to change the window. Activity is
rechecked on every request even while the more expensive usage totals are
cached.

Listening beyond loopback is refused unless a bearer token is configured. The
bridge returns only the display fields below; account email, account ID, OAuth
tokens, session names, and project paths are not exposed.

## Snapshot schema

```json
{
  "schema_version": 1,
  "generated_at": "2026-01-15T12:00:00+01:00",
  "active": true,
  "currency": "USD",
  "limits": {
    "resets_available": 1,
    "primary": {"used_percent": 25, "resets_at": "2026-01-15T16:00:00Z"},
    "secondary": {"used_percent": 40, "resets_at": "2026-01-20T09:00:00Z"}
  },
  "month_to_date": {"cost_usd": 123.45, "total_tokens": 234567890},
  "daily": [
    {"date": "2026-01-15", "cost_usd": 12.34, "total_tokens": 23456789}
  ]
}
```

`limits.resets_available` is the number of banked Codex rate-limit resets that
can be applied from the Codex usage page. Older sources may omit it; the display
then hides the corner badge.

The cost shown from local Codex logs is an estimated API-price equivalent. It
is not an invoice or the amount charged for a ChatGPT subscription.
