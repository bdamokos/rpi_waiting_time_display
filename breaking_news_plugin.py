"""Breaking-news display plugin backed by the shared screen arbiter."""

import logging
import threading
import time
from collections import deque

from breaking_news_display import draw_breaking_news
from breaking_news_service import BreakingNewsWatcher
from plugins import OverrideCapability, normalize_plugin_context
from rss_service import env_int

logger = logging.getLogger(__name__)


class BreakingNewsPlugin:
    name = "breaking-news"
    OWNER = "breaking-news"

    def __init__(
        self,
        epd,
        arbiter=None,
        display_lock=None,
        *,
        watcher=None,
        on_render=None,
        clock=None,
    ):
        context = normalize_plugin_context(epd, arbiter, display_lock, on_render)
        self.context = context
        self.epd = context.epd
        self.arbiter = context.arbiter
        self.display_lock = context.display_lock
        self.watcher = watcher or BreakingNewsWatcher()
        self.on_render = on_render if on_render is not None else context.on_render
        self.clock = clock or time.monotonic
        self.enabled = self.watcher.enabled
        self.poll_seconds = max(60, env_int("breaking_news_poll_seconds", 300))
        self.duration = max(30, env_int("breaking_news_display_seconds", 240))
        self.priority = env_int("breaking_news_priority", 70)
        self.max_queue = max(1, env_int("breaking_news_max_queue", 3))
        self._queue = deque()
        self._active_until = None
        self._rendered_key = None
        self._thread = None
        self._stop_event = threading.Event()

    @property
    def override_capabilities(self):
        return (OverrideCapability(self.OWNER, self.priority),)

    @property
    def display_overrides(self):
        return ()

    def start(self):
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="BreakingNewsPlugin", daemon=True
        )
        self._thread.start()
        logger.info(
            "Breaking-news watcher started for %d feeds",
            len(self.watcher.sources),
        )

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1.0)
            if not self._thread.is_alive():
                self._thread = None
        self.arbiter.release(self.OWNER)

    def _run(self):
        next_poll = 0.0
        while not self._stop_event.is_set():
            now = self.clock()
            if now >= next_poll:
                try:
                    self.add_entries(self.watcher.poll())
                except Exception as exc:
                    logger.warning(
                        "Breaking-news update failed (%s)", type(exc).__name__
                    )
                next_poll = now + self.poll_seconds
            if not self._stop_event.is_set():
                self.tick(now)
            self._stop_event.wait(1.0)

    def add_entries(self, entries):
        known = {entry.key for entry in self._queue}
        for entry in entries:
            if entry.key not in known:
                self._queue.append(entry)
                known.add(entry.key)
        while len(self._queue) > self.max_queue:
            self._queue.popleft()

    def tick(self, now=None):
        now = self.clock() if now is None else now
        if self._active_until is not None and now >= self._active_until:
            if self._queue:
                self._queue.popleft()
            self._active_until = None
            self._rendered_key = None
            self.arbiter.release(self.OWNER)
        if not self._queue:
            self.arbiter.release(self.OWNER)
            return
        if self._active_until is None:
            self._active_until = now + self.duration
        if not self.arbiter.claim(
            self.OWNER, self.priority, max(1, self._active_until - now)
        ):
            return
        entry = self._queue[0]
        if entry.key == self._rendered_key:
            return
        with self.display_lock:
            if not self.arbiter.can_render(self.OWNER):
                return
            draw_breaking_news(self.epd, entry, set_base_image=True)
            self._rendered_key = entry.key
            if self.on_render:
                self.on_render(self.OWNER)
