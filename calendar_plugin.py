"""Calendar display provider backed by the shared screen arbiter."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Callable, Iterable, Optional

from calendar_display import draw_calendar_agenda, draw_upcoming_event
from calendar_service import CalendarClient, CalendarEvent

logger = logging.getLogger(__name__)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


class CalendarPlugin:
    EVENT_OWNER = "calendar-event"
    AGENDA_OWNER = "calendar-agenda"

    def __init__(
        self,
        epd,
        arbiter,
        display_lock,
        *,
        client: Optional[CalendarClient] = None,
        on_render: Optional[Callable[[str], None]] = None,
    ):
        self.epd = epd
        self.arbiter = arbiter
        self.display_lock = display_lock
        self.client = client or CalendarClient()
        self.on_render = on_render
        self.enabled = self.client.enabled
        self.poll_seconds = max(1, int(os.getenv("calendar_poll_seconds", "1")))
        self.claim_ttl = max(5, self.poll_seconds * 3)
        self.lead_minutes = max(0, int(os.getenv("calendar_lead_minutes", "60")))
        self.exclusive_minutes = max(
            0, int(os.getenv("calendar_exclusive_minutes", "10"))
        )
        self.exclusive_enabled = _enabled("calendar_exclusive_enabled", "true")
        self.upcoming_priority = int(os.getenv("calendar_priority_upcoming", "40"))
        self.exclusive_priority = int(os.getenv("calendar_priority_exclusive", "100"))
        self.agenda_priority = int(os.getenv("calendar_priority_agenda", "20"))
        self.agenda_interval = max(
            0, int(os.getenv("calendar_agenda_interval_seconds", "1800"))
        )
        self.agenda_duration = max(
            0, int(os.getenv("calendar_agenda_duration_seconds", "60"))
        )
        self.agenda_max_events = max(
            1, min(4, int(os.getenv("calendar_agenda_max_events", "4")))
        )
        self._event_render_key = None
        self._agenda_render_key = None
        self._event_was_selected = False
        self._agenda_was_selected = False
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if not self.enabled or self._thread:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="CalendarPlugin",
            daemon=True,
        )
        self._thread.start()
        logger.info("Calendar display plugin started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
        self.arbiter.release(self.EVENT_OWNER)
        self.arbiter.release(self.AGENDA_OWNER)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                now = datetime.now(self.client.timezone)
                events = self.client.get_events(now)
                if self._stop_event.is_set():
                    break
                self.tick(now, events)
            except Exception as exc:
                logger.error("Calendar plugin update failed (%s)", type(exc).__name__)
                self.arbiter.release(self.EVENT_OWNER)
                self.arbiter.release(self.AGENDA_OWNER)
            self._stop_event.wait(self.poll_seconds)

    def tick(self, now: datetime, events: Iterable[CalendarEvent]):
        events = sorted(events, key=lambda event: (event.start, event.summary))
        next_event = next(
            (event for event in events if not event.all_day and event.start > now),
            None,
        )
        if next_event:
            seconds_until = (next_event.start - now).total_seconds()
            if seconds_until <= self.lead_minutes * 60:
                self._show_event(now, next_event, seconds_until)
                return

        self.arbiter.release(self.EVENT_OWNER)
        self._event_was_selected = False
        self._event_render_key = None
        self._show_agenda(now, events)

    def _show_event(self, now, event, seconds_until):
        self.arbiter.release(self.AGENDA_OWNER)
        self._agenda_was_selected = False
        exclusive = (
            self.exclusive_enabled
            and not event.stale
            and seconds_until <= self.exclusive_minutes * 60
        )
        priority = self.exclusive_priority if exclusive else self.upcoming_priority
        selected = self.arbiter.claim(
            self.EVENT_OWNER,
            priority,
            self.claim_ttl,
            exclusive=exclusive,
        )
        if not selected:
            self._event_was_selected = False
            return
        minutes = max(0, int((seconds_until + 59) // 60))
        render_key = (event.uid, exclusive, minutes, event.stale)
        if render_key == self._event_render_key and self._event_was_selected:
            return
        with self.display_lock:
            if not self.arbiter.can_render(self.EVENT_OWNER):
                self._event_was_selected = False
                return
            draw_upcoming_event(
                self.epd,
                event,
                now,
                set_base_image=not self._event_was_selected,
            )
        self._event_render_key = render_key
        self._event_was_selected = True
        if self.on_render:
            self.on_render(self.EVENT_OWNER)

    def _show_agenda(self, now, events):
        if not events or not self._agenda_is_due(now):
            self.arbiter.release(self.AGENDA_OWNER)
            self._agenda_was_selected = False
            self._agenda_render_key = None
            return
        selected = self.arbiter.claim(
            self.AGENDA_OWNER,
            self.agenda_priority,
            self.claim_ttl,
        )
        if not selected:
            self._agenda_was_selected = False
            return
        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
        slot = seconds_since_midnight // self.agenda_interval
        render_key = (
            slot,
            tuple(event.uid for event in events[: self.agenda_max_events]),
        )
        if render_key == self._agenda_render_key and self._agenda_was_selected:
            return
        with self.display_lock:
            if not self.arbiter.can_render(self.AGENDA_OWNER):
                self._agenda_was_selected = False
                return
            draw_calendar_agenda(
                self.epd,
                events[: self.agenda_max_events],
                now,
                set_base_image=not self._agenda_was_selected,
            )
        self._agenda_render_key = render_key
        self._agenda_was_selected = True
        if self.on_render:
            self.on_render(self.AGENDA_OWNER)

    def _agenda_is_due(self, now):
        if not self.agenda_interval or not self.agenda_duration:
            return False
        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
        return seconds_since_midnight % self.agenda_interval < self.agenda_duration
