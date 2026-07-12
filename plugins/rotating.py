"""Reusable periodic, arbitrated rotation of plugin-provided screens."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Optional, Sequence

from .context import PluginContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RotatingView:
    """One view in a periodic display rotation."""

    owner: str
    render: Callable[[], Any]
    duration_seconds: float
    priority: int
    exclusive: bool = False
    render_key: Optional[Callable[[], Hashable]] = None

    def __post_init__(self):
        if not self.owner.strip():
            raise ValueError("rotating view owner must not be empty")
        if self.duration_seconds <= 0:
            raise ValueError("rotating view duration_seconds must be positive")
        object.__setattr__(self, "owner", self.owner.strip())
        object.__setattr__(self, "duration_seconds", float(self.duration_seconds))
        object.__setattr__(self, "priority", int(self.priority))


class PeriodicRotatingScreen:
    """Show a sequence of views periodically without bypassing the arbiter."""

    def __init__(
        self,
        context: PluginContext,
        views: Sequence[RotatingView],
        *,
        interval_seconds: float,
        poll_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        stop_event: Optional[threading.Event] = None,
        thread_name: str = "PeriodicRotatingScreen",
    ):
        if not views:
            raise ValueError("periodic rotating screen requires at least one view")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must not be negative")
        if poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        self.context = context
        self.views = tuple(views)
        owners = [view.owner for view in self.views]
        if len(set(owners)) != len(owners):
            raise ValueError("rotating view owners must be unique")
        self.interval_seconds = float(interval_seconds)
        self.poll_seconds = float(poll_seconds)
        self.clock = clock
        self.stop_event = stop_event or threading.Event()
        self.thread_name = thread_name
        self._thread = None
        self._index = 0
        self._view_started_at = None
        self._pending = False
        self._next_rotation_at = 0.0
        self._rendered_key = None
        self._was_selected = False

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name=self.thread_name, daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.poll_seconds * 2))
            if not self._thread.is_alive():
                self._thread = None
        for view in self.views:
            self.context.arbiter.release(view.owner)
        self._view_started_at = None
        self._pending = False
        self._rendered_key = None
        self._was_selected = False

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Periodic rotating screen update failed")
                self._release_current()
            self.stop_event.wait(self.poll_seconds)

    def tick(self, now: Optional[float] = None) -> bool:
        """Advance and render the rotation once; return whether it rendered."""

        now = self.clock() if now is None else now
        if self._view_started_at is None and not self._pending:
            if now < self._next_rotation_at:
                return False
            self._begin_view(0)
        elif self._view_started_at is not None:
            view = self.views[self._index]
            if now >= self._view_started_at + view.duration_seconds:
                self.context.arbiter.release(view.owner)
                next_index = self._index + 1
                if next_index >= len(self.views):
                    self._view_started_at = None
                    self._pending = False
                    self._next_rotation_at = now + self.interval_seconds
                    self._rendered_key = None
                    self._was_selected = False
                    return False
                self._begin_view(next_index)

        view = self.views[self._index]
        remaining = view.duration_seconds
        if self._view_started_at is not None:
            remaining = max(0.001, self._view_started_at + view.duration_seconds - now)
        selected = self.context.arbiter.claim(
            view.owner,
            view.priority,
            remaining,
            exclusive=view.exclusive,
        )
        if not selected:
            self._was_selected = False
            return False

        # A view's duration starts when it first wins the screen, not while it
        # is waiting behind a higher-priority owner.
        if self._view_started_at is None:
            self._view_started_at = now
            self._pending = False

        key = view.render_key() if view.render_key else None
        dedupe_key = (self._index, key)
        if self._was_selected and self._rendered_key == dedupe_key:
            return False

        with self.context.display_lock:
            if not self.context.arbiter.can_render(view.owner):
                self._was_selected = False
                return False
            view.render()

        self._rendered_key = dedupe_key
        self._was_selected = True
        if self.context.on_render:
            self.context.on_render(view.owner)
        return True

    def _begin_view(self, index: int) -> None:
        self._index = index
        self._view_started_at = None
        self._pending = True
        self._rendered_key = None
        self._was_selected = False

    def _release_current(self) -> None:
        if self._view_started_at is not None:
            self.context.arbiter.release(self.views[self._index].owner)
        self._was_selected = False
