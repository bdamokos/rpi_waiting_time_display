"""Recurring YNAB glance backed by the shared screen arbiter."""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from typing import Callable, List, Optional

from ynab_budget import YnabBudgetClient, YnabSnapshot
from ynab_display import draw_ynab_view

logger = logging.getLogger(__name__)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


class YnabGlancePlugin:
    name = "ynab-glance"
    display_overrides = ()
    override_capabilities = ()
    OWNER = "ynab-glance"

    def __init__(
        self,
        epd,
        arbiter,
        display_lock,
        *,
        client: YnabBudgetClient,
        views: List[str],
        on_render: Optional[Callable[[str], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
        is_current: Optional[Callable[[], bool]] = None,
        base_mode_at: Optional[Callable[[datetime], str]] = None,
    ):
        self.epd = epd
        self.arbiter = arbiter
        self.display_lock = display_lock
        self.client = client
        self.views = views
        self.on_render = on_render
        self.on_release = on_release
        self.is_current = is_current
        self.base_mode_at = base_mode_at
        self.enabled = self.client.enabled and _enabled("ynab_glance_enabled")
        self.poll_seconds = max(1, int(os.getenv("ynab_glance_poll_seconds", "1")))
        self.claim_ttl = max(5, self.poll_seconds * 3)
        self.interval = max(
            0, int(os.getenv("ynab_glance_interval_seconds", "1800"))
        )
        configured_duration = max(
            0, int(os.getenv("ynab_glance_duration_seconds", "60"))
        )
        self.duration = min(configured_duration, self.interval) if self.interval else 0
        configured_offset = int(os.getenv("ynab_glance_offset_seconds", "900"))
        self.offset = configured_offset % self.interval if self.interval else 0
        self.priority = int(os.getenv("ynab_glance_priority", "20"))
        self._next_view_index = 0
        self._active_slot = None
        self._active_view = None
        self._active_view_committed = False
        self._render_key = None
        self._was_selected = False
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        if not self.enabled:
            return
        if self._thread and self._thread.is_alive():
            return
        self._thread = None
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="YnabGlancePlugin",
            daemon=True,
        )
        self._thread.start()
        logger.info("YNAB glance plugin started")

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread:
            thread.join(timeout=1.0)
            if not thread.is_alive():
                self._thread = None
        self._release(restore=False)

    def _run(self):
        while not self._stop_event.is_set():
            try:
                now = datetime.now()
                snapshot = self.client.get_snapshot() if self._is_due(now) else None
                now = datetime.now()
                if self._stop_event.is_set():
                    break
                self.tick(now, snapshot)
            except Exception as exc:
                logger.error("YNAB glance update failed (%s)", type(exc).__name__)
                self._release()
            self._stop_event.wait(self.poll_seconds)

    def tick(self, now: datetime, snapshot: Optional[YnabSnapshot]):
        if not self.enabled or not self._is_due(now):
            self._release()
            return
        if snapshot is None:
            self._release()
            return

        slot = self._slot_at(now)
        view = self._view_for_slot(slot)
        remaining = self.duration - self._cycle_position(now)
        selected = self.arbiter.claim(
            self.OWNER,
            self.priority,
            min(self.claim_ttl, max(1, remaining)),
            exclusive=False,
        )
        if not selected:
            self._was_selected = False
            return

        render_key = (slot, view, snapshot.generated_at, snapshot.stale)
        still_displayed = self.is_current() if self.is_current else self._was_selected
        if render_key == self._render_key and self._was_selected and still_displayed:
            return

        with self.display_lock:
            if not self.arbiter.can_render(self.OWNER):
                self._was_selected = False
                return
            draw_ynab_view(
                self.epd,
                snapshot,
                view,
                now=now,
                set_base_image=not self._was_selected or not still_displayed,
            )

        if not self._active_view_committed:
            self._next_view_index = (self._next_view_index + 1) % len(self.views)
            self._active_view_committed = True
        self._render_key = render_key
        self._was_selected = True
        if self.on_render:
            self.on_render(self.OWNER)

    def _is_due(self, now: datetime) -> bool:
        if not self.enabled or not self.interval or not self.duration:
            return False
        if self.base_mode_at:
            mode = self.base_mode_at(now)
            if isinstance(mode, str) and mode.strip().lower() in {
                "ynab",
                "ynab-always",
            }:
                return False
        return self._cycle_position(now) < self.duration

    def _absolute_seconds(self, now: datetime) -> int:
        seconds_since_midnight = now.hour * 3600 + now.minute * 60 + now.second
        return now.toordinal() * 86400 + seconds_since_midnight

    def _cycle_position(self, now: datetime) -> int:
        return (self._absolute_seconds(now) - self.offset) % self.interval

    def _slot_at(self, now: datetime) -> int:
        return (self._absolute_seconds(now) - self.offset) // self.interval

    def _view_for_slot(self, slot: int) -> str:
        if slot != self._active_slot:
            self._active_slot = slot
            self._active_view = self.views[self._next_view_index]
            self._active_view_committed = False
        return self._active_view

    def _release(self, *, restore=True):
        was_active = self.arbiter.release(self.OWNER)
        self._was_selected = False
        self._render_key = None
        if restore and was_active and self.on_release:
            self.on_release()
