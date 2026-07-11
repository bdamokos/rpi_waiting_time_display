import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from calendar_plugin import CalendarPlugin
from calendar_service import CalendarEvent
from screen_arbiter import ScreenArbiter

TIMEZONE = ZoneInfo("Europe/Brussels")


def _event(now, minutes=120, *, stale=False):
    start = now + timedelta(minutes=minutes)
    return CalendarEvent(
        uid=f"event-{minutes}",
        summary="Team review",
        start=start,
        end=start + timedelta(hours=1),
        location="Room 12",
        stale=stale,
    )


def _plugin(monkeypatch, rendered):
    monkeypatch.setenv("calendar_lead_minutes", "60")
    monkeypatch.setenv("calendar_exclusive_minutes", "10")
    monkeypatch.setenv("calendar_exclusive_enabled", "true")
    monkeypatch.setenv("calendar_priority_agenda", "20")
    monkeypatch.setenv("calendar_priority_upcoming", "40")
    monkeypatch.setenv("calendar_priority_exclusive", "100")
    monkeypatch.setenv("calendar_agenda_interval_seconds", "1800")
    monkeypatch.setenv("calendar_agenda_duration_seconds", "60")
    monkeypatch.setattr(
        "calendar_plugin.draw_upcoming_event",
        lambda *args, **kwargs: rendered.append(("event", kwargs)),
    )
    monkeypatch.setattr(
        "calendar_plugin.draw_calendar_agenda",
        lambda *args, **kwargs: rendered.append(("agenda", kwargs)),
    )
    client = SimpleNamespace(enabled=True, timezone=TIMEZONE)
    return CalendarPlugin(
        object(),
        ScreenArbiter(),
        threading.Lock(),
        client=client,
    )


def test_upcoming_event_claim_is_preemptible(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    now = datetime(2026, 7, 11, 8, 5, tzinfo=TIMEZONE)

    plugin.tick(now, [_event(now, 30)])

    claim = plugin.arbiter.claim_for(plugin.EVENT_OWNER)
    assert claim.priority == 40
    assert claim.exclusive is False
    assert plugin.arbiter.claim("flight", 50, 30)
    assert plugin.arbiter.active_owner() == "flight"
    assert rendered[0][0] == "event"


def test_fresh_event_is_exclusive_in_final_ten_minutes(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    now = datetime(2026, 7, 11, 8, 5, tzinfo=TIMEZONE)

    plugin.tick(now, [_event(now, 5)])

    claim = plugin.arbiter.claim_for(plugin.EVENT_OWNER)
    assert claim.priority == 100
    assert claim.exclusive is True
    assert not plugin.arbiter.claim("flight", 200, 30)
    assert plugin.arbiter.active_owner() == plugin.EVENT_OWNER


def test_stale_event_never_takes_exclusive_control(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    now = datetime(2026, 7, 11, 8, 5, tzinfo=TIMEZONE)

    plugin.tick(now, [_event(now, 5, stale=True)])

    claim = plugin.arbiter.claim_for(plugin.EVENT_OWNER)
    assert claim.exclusive is False
    assert plugin.arbiter.claim("flight", 50, 30)
    assert plugin.arbiter.active_owner() == "flight"


def test_agenda_glance_releases_after_configured_minute(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    start = datetime(2026, 7, 11, 8, 0, tzinfo=TIMEZONE)
    event = _event(start, 120)

    plugin.tick(start, [event])
    assert plugin.arbiter.active_owner() == plugin.AGENDA_OWNER
    assert rendered[0][0] == "agenda"

    plugin.tick(start + timedelta(seconds=60), [event])
    assert plugin.arbiter.active_owner() is None


def test_event_start_releases_exclusive_claim(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    now = datetime(2026, 7, 11, 8, 5, tzinfo=TIMEZONE)
    event = _event(now, 5)
    plugin.tick(now, [event])
    assert plugin.arbiter.active_owner() == plugin.EVENT_OWNER

    plugin.tick(event.start, [event])

    assert plugin.arbiter.active_owner() is None


def test_all_day_event_only_appears_in_agenda(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    now = datetime(2026, 7, 11, 8, 0, tzinfo=TIMEZONE)
    event = CalendarEvent(
        uid="all-day",
        summary="Birthday",
        start=now + timedelta(minutes=5),
        end=now + timedelta(days=1),
        all_day=True,
    )

    plugin.tick(now, [event])

    assert plugin.arbiter.active_owner() == plugin.AGENDA_OWNER
    assert rendered[0][0] == "agenda"
