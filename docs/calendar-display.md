# Calendar display

The optional calendar plugin reads one or more iCalendar (`.ics`) feeds and
adds two screen types:

- an event card during the configured lead window (60 minutes by default);
- a short upcoming-agenda glance every configured interval (one minute every
  half hour by default).

Set `calendar_default_enabled=true` to keep the upcoming agenda as the preferred
base screen whenever useful events exist outside the commuting window. The
plugin uses the raw `display_schedule` mode to define that window. By default,
`calendar_default_modes=auto,weather,token,token-always`, so scheduled `transit`
periods keep the bus display while other periods prefer the calendar. Change
the comma-separated mode list to fit another installation's schedule, or leave
the feature disabled to retain glance-only behavior. The preferred agenda
refreshes its clock every `calendar_default_refresh_seconds` (90 seconds by
default) without relinquishing its low-priority claim.

The final ten minutes before a fresh event are exclusive by default. Earlier
event cards use priority `40`, so the default flight (`50`) and ISS (`60`)
claims can temporarily override them. Agenda glances use priority `20` and
return automatically to the scheduled transit, weather, or token screen. A
preferred default agenda uses the same low priority, so higher-priority plugin
claims remain able to interrupt it. The normal lead-window event card and its
exclusive final-ten-minute behavior are unchanged.

## Google Calendar setup (recommended)

Use the Google Calendar Events API on a Raspberry Pi. It applies `timeMin` and
`timeMax` at the server, asks Google to expand recurring events and exceptions
with `singleEvents=true`, and caps each calendar at
`calendar_google_max_events`. The response and last-good cache therefore stay
proportional to the next few days, not to the age of the calendar.

1. Enable the Google Calendar API in a Google Cloud project and create a
   service account key.
2. Store the downloaded JSON key outside this repository with owner-only file
   permissions.
3. Share each calendar read-only with the service account's `client_email`.
4. Copy each calendar ID from **Settings > Integrate calendar** into the
   untracked `.env`. Calendar IDs and key paths are never logged.

```dotenv
calendar_enabled=true
calendar_source=google_api
calendar_google_credentials_file=/home/bence/.config/display/calendar-reader.json
calendar_google_calendar_ids=REDACTED_CALENDAR_ID
calendar_google_max_events=100
calendar_timezone=Europe/Brussels
calendar_lookahead_days=3
```

Use comma-separated `calendar_google_calendar_ids` for multiple calendars. A
Workspace administrator may instead grant domain-wide delegation; set
`calendar_google_delegated_user` only when that has been intentionally
configured. The implementation requests only the
`calendar.events.readonly` OAuth scope.

### Migrating from a Google secret ICS URL

Replace `calendar_source=ics` and `calendar_ics_urls=...` with the API settings
above. Do not enable the calendar again on a memory-limited Pi until the service
account can retrieve the bounded API window. The secret ICS address can then be
removed from `.env` and revoked if it may have been exposed.

HTTP ICS remains available for small non-Google calendars, and `file` remains
available for externally synchronized files. Both are legacy compatibility
paths: an ICS feed has no standard `timeMin`/`timeMax` request, and recurrence
masters, exceptions, and `VTIMEZONE` definitions may be separated anywhere in
the file. Pre-filtering VEVENT blocks before a standards-compliant parse can
therefore silently lose or mis-time occurrences. The application must parse an
entire ICS source to preserve those semantics, so do not point the ICS mode at
a large historical Google feed on a constrained device.

For development or an externally synchronized feed, use `calendar_source=file`
with `calendar_ics_file` or comma-separated `calendar_ics_files` paths.

## Refresh and failure behavior

Sources refresh every five minutes by default. Google API calls are bounded by
the requested time window and event cap; HTTP ICS feeds use ETag/Last-Modified
conditional requests when available. Successful bounded API results or ICS
responses are cached under `cache/` with owner-only permissions. If a source is
temporarily unavailable, the plugin may show its last-good events as stale for
`calendar_max_stale_seconds`, but stale events never receive the exclusive
pre-event lease.

Cancelled events are ignored. All-day events are excluded by default; when
enabled, they appear only in the agenda and never take a pre-event lease. Set
`calendar_show_details=false` to render every item as `Busy` without its
location.

See `.env.example` for all timing, priority, privacy, and agenda settings.
