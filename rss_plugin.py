"""RSS watcher display plugin backed by the shared screen arbiter."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from rss_display import draw_feed_entry
from plugins import OverrideCapability, normalize_plugin_context
from rss_service import RSSWatcher, env_int

logger = logging.getLogger(__name__)


class RSSPlugin:
    name = "rss"
    OWNER = "rss-watch"

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
        self.watcher = watcher or RSSWatcher()
        self.on_render = on_render if on_render is not None else context.on_render
        self.clock = clock or time.monotonic
        self.enabled = self.watcher.enabled
        self.poll_seconds = max(15, env_int("rss_watch_poll_seconds", 60))
        self.duration = max(5, env_int("rss_watch_display_seconds", 60))
        self.priority = env_int("rss_watch_priority", 30)
        self.max_queue = max(1, env_int("rss_watch_max_queue", 10))
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
        self._thread = threading.Thread(target=self._run, name="RSSPlugin", daemon=True)
        self._thread.start()
        logger.info("RSS watcher started for %d feeds", len(self.watcher.sources))

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
                    logger.warning("RSS watcher update failed (%s)", type(exc).__name__)
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
        remaining = max(1, self._active_until - now)
        if not self.arbiter.claim(self.OWNER, self.priority, remaining):
            return
        entry = self._queue[0]
        if entry.key == self._rendered_key:
            return
        avatar = None
        if entry.avatar_url:
            try:
                response = self.watcher.session.get(
                    entry.avatar_url,
                    timeout=self.watcher.timeout,
                    stream=True,
                )
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_content(chunk_size=16_384):
                    content.extend(chunk)
                    if len(content) > 512_000:
                        break
                else:
                    avatar = bytes(content)
            except Exception:
                logger.debug("RSS avatar unavailable", exc_info=True)
        with self.display_lock:
            if not self.arbiter.can_render(self.OWNER):
                return
            draw_feed_entry(self.epd, entry, avatar_bytes=avatar, set_base_image=True)
            self._rendered_key = entry.key
            if self.on_render:
                self.on_render(self.OWNER)
