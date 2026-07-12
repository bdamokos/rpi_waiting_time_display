import stat
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from calendar_service import (CalendarClient, GoogleCalendarApiSource,
                              GoogleTasksApiSource, IcsCalendarSource,
                              parse_ics_events)

TIMEZONE = ZoneInfo("Europe/Brussels")
NOW = datetime(2026, 7, 11, 8, 0, tzinfo=TIMEZONE)
ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:standup
DTSTART;TZID=Europe/Brussels:20260706T100000
DTEND;TZID=Europe/Brussels:20260706T103000
RRULE:FREQ=WEEKLY;COUNT=4
SUMMARY:Weekly standup
LOCATION:Room 12
END:VEVENT
BEGIN:VEVENT
UID:all-day
DTSTART;VALUE=DATE:20260711
DTEND;VALUE=DATE:20260712
SUMMARY:Birthday
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTART;TZID=Europe/Brussels:20260712T120000
DTEND;TZID=Europe/Brussels:20260712T130000
SUMMARY:Cancelled meeting
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""


class FakeResponse:
    def __init__(self, status_code, text="", headers=None, json_data=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.json_data = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self.json_data is None:
            raise ValueError("no JSON response")
        return self.json_data


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


class FakeCredentials:
    valid = True
    token = "test-token"


def _task(index, *, day=13):
    return {
        "id": f"task-{index}",
        "title": f"Task {index}",
        "status": "needsAction",
        "due": f"2026-07-{day:02d}T00:00:00.000Z",
    }


def test_google_tasks_requests_bounded_due_window_and_normalizes(tmp_path):
    session = FakeSession(
        [
            FakeResponse(
                200, json_data={"items": [{"id": "default", "title": "My Tasks"}]}
            ),
            FakeResponse(200, json_data={"items": [_task(1)]}),
        ]
    )
    source = GoogleTasksApiSource(
        credentials_file=tmp_path / "unused.json",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        session=session,
        credentials=FakeCredentials(),
    )
    events = source.events_between(
        NOW,
        NOW + timedelta(days=3),
        timezone=TIMEZONE,
        include_all_day=True,
        show_details=True,
    )
    assert [event.summary for event in events] == ["☐ Task 1"]
    assert events[0].location == "My Tasks"
    params = session.calls[1][1]["params"]
    assert params["dueMin"] == "2026-07-10T22:00:00Z"
    assert params["dueMax"] == "2026-07-13T22:00:00Z"
    assert stat.S_IMODE(source.cache_file.stat().st_mode) == 0o600


def test_google_tasks_hides_details_and_skips_completed_or_undated(tmp_path):
    events = GoogleTasksApiSource._normalize(
        [
            _task(1),
            {**_task(2), "status": "completed"},
            {"id": "undated", "title": "Later"},
        ],
        NOW,
        NOW + timedelta(days=3),
        TIMEZONE,
        False,
        stale=False,
    )
    assert [event.summary for event in events] == ["Task"]


def test_parser_expands_recurring_events_and_skips_cancelled():
    events = parse_ics_events(
        ICS,
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert [event.start.day for event in events] == [13, 20]
    assert all(event.summary == "Weekly standup" for event in events)
    assert all(event.location == "Room 12" for event in events)


def test_parser_can_include_current_all_day_events_and_hide_details():
    events = parse_ics_events(
        ICS,
        NOW,
        NOW + timedelta(days=2),
        timezone=TIMEZONE,
        include_all_day=True,
        show_details=False,
    )

    assert len(events) == 1
    assert events[0].all_day is True
    assert events[0].summary == "Busy"
    assert events[0].location == ""


def test_http_source_uses_conditional_requests_and_private_cache(tmp_path):
    session = FakeSession(
        [
            FakeResponse(200, ICS, {"ETag": '"v1"'}),
            FakeResponse(304),
        ]
    )
    source = IcsCalendarSource(
        "https://calendar.example/secret/basic.ics",
        source_type="ics",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        session=session,
    )

    first = source.events_between(
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )
    second = source.events_between(
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert len(first) == len(second) == 2
    assert session.calls[1][1]["headers"]["If-None-Match"] == '"v1"'
    assert stat.S_IMODE(source.cache_file.stat().st_mode) == 0o600


def test_http_failure_uses_stale_cache_without_logging_secret(tmp_path, caplog):
    locator = "https://calendar.example/very-secret/basic.ics"
    successful = IcsCalendarSource(
        locator,
        source_type="ics",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        session=FakeSession([FakeResponse(200, ICS)]),
    )
    successful.events_between(
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )
    failing = IcsCalendarSource(
        locator,
        source_type="ics",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        session=FakeSession([requests.ConnectionError("offline")]),
    )

    events = failing.events_between(
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert len(events) == 2
    assert all(event.stale for event in events)
    assert "very-secret" not in caplog.text


def test_malformed_http_response_does_not_replace_last_good_cache(tmp_path):
    locator = "https://calendar.example/secret/basic.ics"
    source = IcsCalendarSource(
        locator,
        source_type="ics",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        session=FakeSession(
            [
                FakeResponse(200, ICS, {"ETag": '"v1"'}),
                FakeResponse(200, "not a calendar", {"ETag": '"broken"'}),
            ]
        ),
    )
    source.events_between(
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    events = source.events_between(
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert len(events) == 2
    assert all(event.stale for event in events)
    assert source.cache_file.read_text(encoding="utf-8") == ICS


def test_file_source_reads_local_ics(tmp_path):
    path = tmp_path / "calendar.ics"
    path.write_text(ICS, encoding="utf-8")
    source = IcsCalendarSource(
        str(path),
        source_type="file",
        cache_dir=Path(tmp_path),
        timeout=5,
        max_stale_seconds=3600,
    )

    events = source.events_between(
        NOW,
        NOW + timedelta(days=12),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert len(events) == 2
    assert all(not event.stale for event in events)


def _api_event(index, *, day=12):
    return {
        "id": f"instance-{index}",
        "iCalUID": "weekly@example.test",
        "status": "confirmed",
        "summary": f"Meeting {index}",
        "start": {"dateTime": f"2026-07-{day:02d}T10:00:00+02:00"},
        "end": {"dateTime": f"2026-07-{day:02d}T10:30:00+02:00"},
    }


def test_google_api_requests_bounded_server_expanded_window(tmp_path):
    session = FakeSession([FakeResponse(200, json_data={"items": [_api_event(1)]})])
    source = GoogleCalendarApiSource(
        "private-calendar@example.test",
        credentials_file=tmp_path / "unused.json",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        max_events=20,
        session=session,
        credentials=FakeCredentials(),
    )

    events = source.events_between(
        NOW,
        NOW + timedelta(days=3),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert len(events) == 1
    url, request = session.calls[0]
    assert "@" not in url
    assert "%40" in url
    assert request["params"]["timeMin"] == NOW.isoformat()
    assert request["params"]["timeMax"] == (NOW + timedelta(days=3)).isoformat()
    assert request["params"]["singleEvents"] == "true"
    assert request["params"]["orderBy"] == "startTime"
    assert request["params"]["maxResults"] == 20


def test_google_api_caps_pagination_and_private_cache_size(tmp_path):
    session = FakeSession(
        [
            FakeResponse(
                200,
                json_data={
                    "items": [_api_event(index) for index in range(80)],
                    "nextPageToken": "more",
                },
            )
        ]
    )
    source = GoogleCalendarApiSource(
        "calendar-id",
        credentials_file=tmp_path / "unused.json",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        max_events=25,
        session=session,
        credentials=FakeCredentials(),
    )

    events = source.events_between(
        NOW,
        NOW + timedelta(days=3),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert len(events) == 25
    assert len(session.calls) == 1
    assert source.cache_file.stat().st_size < 20_000
    assert stat.S_IMODE(source.cache_file.stat().st_mode) == 0o600


def test_google_api_uses_stale_bounded_cache(tmp_path):
    source = GoogleCalendarApiSource(
        "calendar-id",
        credentials_file=tmp_path / "unused.json",
        cache_dir=tmp_path,
        timeout=5,
        max_stale_seconds=3600,
        session=FakeSession(
            [
                FakeResponse(200, json_data={"items": [_api_event(1)]}),
                requests.ConnectionError("offline"),
            ]
        ),
        credentials=FakeCredentials(),
    )
    source.events_between(
        NOW,
        NOW + timedelta(days=3),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    events = source.events_between(
        NOW,
        NOW + timedelta(days=3),
        timezone=TIMEZONE,
        include_all_day=False,
        show_details=True,
    )

    assert len(events) == 1
    assert events[0].stale is True


def test_calendar_client_reads_configured_file_source(tmp_path, monkeypatch):
    path = tmp_path / "calendar.ics"
    path.write_text(ICS, encoding="utf-8")
    monkeypatch.setenv("calendar_enabled", "true")
    monkeypatch.setenv("calendar_source", "file")
    monkeypatch.setenv("calendar_ics_file", str(path))
    monkeypatch.setenv("calendar_timezone", "Europe/Brussels")
    monkeypatch.setenv("calendar_lookahead_days", "12")

    events = CalendarClient().get_events(NOW, force=True)

    assert [event.start.day for event in events] == [13, 20]


def test_invalid_source_timeout_does_not_crash_startup(monkeypatch, caplog):
    monkeypatch.setenv("calendar_enabled", "true")
    monkeypatch.setenv("calendar_source", "ics")
    monkeypatch.setenv("calendar_ics_url", "https://calendar.example/basic.ics")
    monkeypatch.setenv("calendar_timeout", "not-a-number")

    client = CalendarClient()

    assert client._sources == []
    assert "Invalid calendar configuration" in caplog.text
