# Home Assistant display plugin

The optional Home Assistant plugin bootstraps configured entity states through
REST, then subscribes to `state_changed` events over the authenticated WebSocket
API. It is disabled by default.

Set `home_assistant_enabled=true`, `home_assistant_url`,
`home_assistant_token`, and `home_assistant_config` in the ignored `.env` file.
The config accepts inline JSON or a path; `docs/home-assistant-example.json`
uses reserved example entities.

Screen types are `temperatures`, `lights`, `climate`, `paired`, and `entities`.
Empty screens are skipped. Cards default to 30 seconds before returning to the
base display for three minutes. Triggers can claim a target screen on an
inactive-to-active transition with configurable debounce, priority and TTL.

An entity row may use `entity_ids` instead of `entity_id` to group binary
sensors. The row is active when any available member is active and clear only
when every available member is clear. List each member separately in `triggers`
when either member should claim the screen.

Tokens and household entity IDs belong only in ignored deployment config. The
service does not log URLs, tokens, headers, or authentication payloads.
Unavailable updates retain the previous useful value with a stale marker.
The lights card keeps the normal four-row font size and paginates additional
active rows. Pages default to 15 seconds and can be adjusted per screen with
`page_seconds`; the screen duration expands when needed so every page is shown.
