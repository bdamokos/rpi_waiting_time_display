"""First-class Home Assistant rotating-screen plugin."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path

from home_assistant_display import (
    draw_home_assistant_screen,
    light_page_count,
    screen_has_content,
)
from home_assistant_models import parse_config
from home_assistant_service import HomeAssistantService
from plugins import OverrideCapability

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _Takeover:
    screen: object
    priority: int
    duration_seconds: float
    started_at: float | None = None


def load_home_assistant_config(value):
    if not value:
        raise ValueError(
            "home_assistant_config is required when Home Assistant is enabled"
        )
    stripped = value.strip()
    data = (
        json.loads(stripped)
        if stripped.startswith(("{", "["))
        else json.loads(Path(stripped).read_text())
    )
    return parse_config(data)


class HomeAssistantPlugin:
    name = "home-assistant"
    display_overrides = ()

    def __init__(
        self,
        context,
        *,
        config,
        service,
        enabled=True,
        clock=time.monotonic,
        poll_seconds=1.0,
    ):
        self.context = context
        self.config = config
        self.service = service
        self.enabled = enabled
        self.clock = clock
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread = None
        self._screen_index = 0
        self._screen_started = None
        self._next_cycle = 0.0
        self._last_key = None
        self._takeovers = {}
        self._last_trigger = {}
        self._pending_triggers = {}
        self._delayed_triggers = {}
        self._state_lock = threading.RLock()
        service.add_listener(self._state_changed)

    @classmethod
    def from_env(cls, context):
        enabled = os.getenv("home_assistant_enabled", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not enabled:
            return None
        config = load_home_assistant_config(os.getenv("home_assistant_config", ""))
        ids = {
            entity_id
            for screen in config.screens
            for entity in screen.entities
            for entity_id in entity.source_entity_ids
        }
        ids.update(trigger.entity_id for trigger in config.triggers)
        service = HomeAssistantService(
            os.environ["home_assistant_url"], os.environ["home_assistant_token"], ids
        )
        return cls(context, config=config, service=service)

    @property
    def override_capabilities(self):
        result = [
            OverrideCapability(f"ha:{screen.screen_id}", screen.priority)
            for screen in self.config.screens
        ]
        result.extend(
            OverrideCapability(f"ha-event:{trigger.screen_id}", trigger.priority)
            for trigger in self.config.triggers
        )
        return tuple(result)

    def start(self):
        if not self.enabled or (self._thread and self._thread.is_alive()):
            return
        self._stop.clear()
        self.service.start()
        self._thread = threading.Thread(
            target=self._run, name="HomeAssistantDisplay", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.service.stop()
        if self._thread:
            self._thread.join(timeout=max(2, self.poll_seconds * 2))
            if not self._thread.is_alive():
                self._thread = None
        with self._state_lock:
            self._pending_triggers.clear()
            self._delayed_triggers.clear()
            self._takeovers.clear()
        for capability in self.override_capabilities:
            self.context.arbiter.release(capability.owner)

    def _run(self):
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Home Assistant display update failed")
            self._stop.wait(self.poll_seconds)

    def _visible(self):
        states = self.service.snapshot()
        return [
            screen
            for screen in self.config.screens
            if screen_has_content(screen, states)
        ]

    def tick(self, now=None):
        now = self.clock() if now is None else now
        states = self.service.snapshot()
        self._activate_ready_triggers(states, now)
        self._activate_delayed_triggers(now)
        with self._state_lock:
            takeovers = tuple(self._takeovers.values())
        for takeover in takeovers:
            if (
                takeover.started_at is not None
                and now >= takeover.started_at + takeover.duration_seconds
            ):
                self.context.arbiter.release(f"ha-event:{takeover.screen.screen_id}")
                with self._state_lock:
                    if self._takeovers.get(takeover.screen.screen_id) is takeover:
                        self._takeovers.pop(takeover.screen.screen_id, None)
        with self._state_lock:
            takeovers = tuple(self._takeovers.values())
        if takeovers:
            rendered_any = False
            for takeover in takeovers:
                ttl = (
                    takeover.duration_seconds
                    if takeover.started_at is None
                    else takeover.started_at + takeover.duration_seconds - now
                )
                rendered_any = (
                    self._render(
                        takeover.screen,
                        states,
                        now,
                        takeover.priority,
                        ttl,
                        event=True,
                    )
                    or rendered_any
                )
                owner = f"ha-event:{takeover.screen.screen_id}"
                if (
                    takeover.started_at is None
                    and self.context.arbiter.active_owner() == owner
                ):
                    with self._state_lock:
                        if self._takeovers.get(takeover.screen.screen_id) is takeover:
                            self._takeovers[takeover.screen.screen_id] = replace(
                                takeover, started_at=now
                            )
            return rendered_any
        screens = self._visible()
        if not screens or now < self._next_cycle:
            return False
        self._screen_index %= len(screens)
        screen = screens[self._screen_index]
        screen_duration = self._screen_duration(screen, states)
        if (
            self._screen_started is not None
            and now >= self._screen_started + screen_duration
        ):
            self.context.arbiter.release(f"ha:{screen.screen_id}")
            self._screen_index += 1
            self._screen_started = now
            if self._screen_index >= len(screens):
                self._screen_index = 0
                self._screen_started = None
                self._next_cycle = now + self.config.interval_seconds
                return False
            screen = screens[self._screen_index]
            screen_duration = self._screen_duration(screen, states)
        remaining = (
            screen_duration
            if self._screen_started is None
            else max(0.1, self._screen_started + screen_duration - now)
        )
        rendered = self._render(screen, states, now, screen.priority, remaining)
        if (
            self._screen_started is None
            and self.context.arbiter.active_owner() == f"ha:{screen.screen_id}"
        ):
            self._screen_started = now
        return rendered

    @staticmethod
    def _screen_duration(screen, states):
        if screen.type != "lights":
            return screen.duration_seconds
        return max(
            screen.duration_seconds,
            screen.page_seconds * light_page_count(screen, states),
        )

    def _render(self, screen, states, now, priority, ttl, event=False):
        owner = f"ha-event:{screen.screen_id}" if event else f"ha:{screen.screen_id}"
        if not self.context.arbiter.claim(owner, priority, ttl):
            return False
        page = 0
        if screen.type == "lights" and self._screen_started is not None:
            page = int((now - self._screen_started) // screen.page_seconds)
            page %= light_page_count(screen, states)
        key = (
            owner,
            page,
            tuple(
                (entity_id, states.get(entity_id))
                for entity in screen.entities
                for entity_id in entity.source_entity_ids
            ),
        )
        if key == self._last_key:
            return False
        with self.context.display_lock:
            if not self.context.arbiter.can_render(owner):
                return False
            draw_home_assistant_screen(
                self.context.epd,
                screen,
                states,
                stale_seconds=self.config.stale_seconds,
                now_monotonic=now,
                page=page,
            )
        self._last_key = key
        if self.context.on_render:
            self.context.on_render(owner)
        return True

    def _activate_ready_triggers(self, states, now):
        with self._state_lock:
            pending = tuple(self._pending_triggers.items())
        for trigger, active_since in pending:
            current = states.get(trigger.entity_id)
            current_state = str(current.state).lower() if current else ""
            if current_state not in trigger.active_states:
                with self._state_lock:
                    self._pending_triggers.pop(trigger, None)
                continue
            if now - active_since < trigger.active_for_seconds:
                continue
            with self._state_lock:
                if self._pending_triggers.pop(trigger, None) is None:
                    continue
                self._queue_trigger(trigger, now)

    def _activate_delayed_triggers(self, now):
        with self._state_lock:
            delayed = tuple(self._delayed_triggers.items())
        for trigger, ready_at in delayed:
            if now < ready_at:
                continue
            with self._state_lock:
                if self._delayed_triggers.pop(trigger, None) is None:
                    continue
                self._activate_trigger(trigger)

    def _queue_trigger(self, trigger, now):
        self._last_trigger[trigger.entity_id] = now
        if trigger.delay_seconds > 0:
            self._delayed_triggers[trigger] = now + trigger.delay_seconds
            return
        self._activate_trigger(trigger)

    def _activate_trigger(self, trigger):
        screen = next(
            screen
            for screen in self.config.screens
            if screen.screen_id == trigger.screen_id
        )
        existing = self._takeovers.get(screen.screen_id)
        if existing and existing.priority > trigger.priority:
            return
        self._takeovers[screen.screen_id] = _Takeover(
            screen=screen,
            priority=trigger.priority,
            duration_seconds=trigger.duration_seconds,
        )
        self._last_key = None

    def _state_changed(self, entity_id, previous, current):
        now = self.clock()
        for trigger in self.config.triggers:
            if trigger.entity_id != entity_id:
                continue
            before = str(previous.state).lower() if previous else ""
            after = str(current.state).lower() if current else ""
            if after not in trigger.active_states:
                with self._state_lock:
                    self._pending_triggers.pop(trigger, None)
                continue
            if before in trigger.active_states:
                continue
            with self._state_lock:
                if self._stop.is_set():
                    return
                last_trigger_time = self._last_trigger.get(entity_id, float("-inf"))
                if now - last_trigger_time < trigger.debounce_seconds:
                    continue
                if trigger.active_for_seconds > 0:
                    self._pending_triggers[trigger] = now
                else:
                    self._queue_trigger(trigger, now)
