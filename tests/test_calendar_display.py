from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from PIL import Image

from calendar_display import draw_calendar_agenda, draw_upcoming_event
from calendar_service import CalendarEvent
from display_adapter import MockDisplay


def test_calendar_views_render_at_display_dimensions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    timezone = ZoneInfo("Europe/Brussels")
    now = datetime(2026, 7, 11, 8, 0, tzinfo=timezone)
    event = CalendarEvent(
        uid="review",
        summary="A fairly long team review title that needs wrapping",
        start=now + timedelta(minutes=10),
        end=now + timedelta(minutes=40),
        location="Meeting room 12",
    )
    display = MockDisplay()

    draw_upcoming_event(display, event, now, set_base_image=True)
    upcoming = Image.open("debug_output.png")
    assert upcoming.size == (display.height, display.width)

    draw_calendar_agenda(display, [event], now, set_base_image=True)
    agenda = Image.open("debug_output.png")
    assert agenda.size == (display.height, display.width)
