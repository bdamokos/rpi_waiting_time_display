# Calendar display

The optional calendar plugin reads one or more iCalendar (`.ics`) feeds and
adds two screen types:

- an event card during the configured lead window (60 minutes by default);
- a short upcoming-agenda glance every configured interval (one minute every
  half hour by default).

The final ten minutes before a fresh event are exclusive by default. Earlier
event cards use priority `40`, so the default flight (`50`) and ISS (`60`)
claims can temporarily override them. Agenda glances use priority `20` and
return automatically to the scheduled transit, weather, or token screen.

## Google Calendar setup

Google Calendar does not require an OAuth client for this read-only use case.
On a computer, open the calendar's settings, choose **Integrate calendar**, and
copy its **Secret address in iCal format**. Google documents the steps in
[Sync your calendar with computer programs](https://support.google.com/calendar/answer/37648).

Store the address only in the untracked `.env` file:

```dotenv
calendar_enabled=true
calendar_source=ics
calendar_ics_urls=https://calendar.google.com/calendar/ical/REDACTED/basic.ics
calendar_timezone=Europe/Brussels
```

Use a comma-separated `calendar_ics_urls` value for multiple calendars. The
secret URL is effectively a read-only bearer credential. Never commit it or
paste it into logs. Reset the secret address in Google Calendar if it is
exposed. A Workspace administrator may disable secret addresses; in that case
an authenticated Calendar API or an external bridge such as
[`gog`](https://github.com/steipete/gogcli) is the fallback, but it requires a
Google Cloud OAuth client and persistent token/keyring setup.

For development or an externally synchronized feed, use `calendar_source=file`
with `calendar_ics_file` or comma-separated `calendar_ics_files` paths.

## Refresh and failure behavior

HTTP feeds refresh every five minutes by default and use ETag/Last-Modified
conditional requests when available. Successful responses are cached under
`cache/` with owner-only permissions. If a source is temporarily unavailable,
the plugin may show its last-good events as stale for
`calendar_max_stale_seconds`, but stale events never receive the exclusive
pre-event lease.

Cancelled events are ignored. All-day events are excluded by default; when
enabled, they appear only in the agenda and never take a pre-event lease. Set
`calendar_show_details=false` to render every item as `Busy` without its
location.

See `.env.example` for all timing, priority, privacy, and agenda settings.
