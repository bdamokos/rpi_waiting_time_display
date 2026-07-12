"""Home Assistant REST bootstrap and WebSocket state subscription."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, Optional

import requests

logger = logging.getLogger(__name__)
UNAVAILABLE = {"unknown", "unavailable", "none", ""}


@dataclass(frozen=True)
class EntityState:
    entity_id: str
    state: Optional[str]
    attributes: dict
    updated_at: datetime
    received_monotonic: float
    available: bool = True

    @classmethod
    def from_message(cls, data, now=None, monotonic=None):
        raw = data.get("state")
        available = raw is not None and str(raw).strip().lower() not in UNAVAILABLE
        stamp = data.get("last_updated") or data.get("last_changed")
        try:
            updated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            updated = datetime.now(timezone.utc)
        return cls(
            entity_id=str(data.get("entity_id", "")),
            state=None if raw is None else str(raw),
            attributes=dict(data.get("attributes") or {}),
            updated_at=updated,
            received_monotonic=time.monotonic() if monotonic is None else monotonic,
            available=available,
        )


class HomeAssistantService:
    """Maintain last-good state for a configured entity subset."""

    def __init__(
        self,
        base_url: str,
        token: str,
        entity_ids: Iterable[str],
        *,
        request_get=requests.get,
        websocket_factory=None,
        clock=time.monotonic,
        reconnect_min=1.0,
        reconnect_max=60.0,
    ):
        if not base_url or not token:
            raise ValueError("Home Assistant URL and token are required")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.entity_ids = frozenset(entity_ids)
        self._request_get = request_get
        self._websocket_factory = websocket_factory or self._default_websocket
        self._clock = clock
        self._reconnect_min = reconnect_min
        self._reconnect_max = reconnect_max
        self._states: Dict[str, EntityState] = {}
        self._listeners = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._socket = None

    def add_listener(
        self, listener: Callable[[str, Optional[EntityState], EntityState], None]
    ):
        self._listeners.append(listener)

    def snapshot(self) -> Dict[str, EntityState]:
        with self._lock:
            return dict(self._states)

    def get(self, entity_id: str) -> Optional[EntityState]:
        with self._lock:
            return self._states.get(entity_id)

    def bootstrap(self) -> None:
        response = self._request_get(
            f"{self.base_url}/api/states",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=15,
        )
        response.raise_for_status()
        for item in response.json():
            entity_id = item.get("entity_id")
            if entity_id in self.entity_ids:
                self._store(item, notify=False)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="HomeAssistant", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._stop.set()
        socket = self._socket
        if socket:
            try:
                socket.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)
            if not self._thread.is_alive():
                self._thread = None

    def _default_websocket(self, url):
        import websocket

        return websocket.create_connection(url, timeout=30, enable_multithread=True)

    def _run(self):
        delay = self._reconnect_min
        while not self._stop.is_set():
            try:
                self.bootstrap()
                self._subscribe()
                delay = self._reconnect_min
            except Exception as exc:
                if not self._stop.is_set():
                    logger.warning(
                        "Home Assistant connection failed (%s); retrying",
                        type(exc).__name__,
                    )
            self._stop.wait(delay)
            delay = min(self._reconnect_max, max(self._reconnect_min, delay * 2))

    def _subscribe(self):
        url = self.base_url.replace("https://", "wss://", 1).replace(
            "http://", "ws://", 1
        )
        socket = self._websocket_factory(f"{url}/api/websocket")
        self._socket = socket
        try:
            hello = json.loads(socket.recv())
            if hello.get("type") != "auth_required":
                raise RuntimeError("unexpected Home Assistant authentication handshake")
            socket.send(json.dumps({"type": "auth", "access_token": self._token}))
            authenticated = json.loads(socket.recv())
            if authenticated.get("type") != "auth_ok":
                raise RuntimeError("Home Assistant authentication failed")
            socket.send(
                json.dumps(
                    {"id": 1, "type": "subscribe_events", "event_type": "state_changed"}
                )
            )
            while not self._stop.is_set():
                message = json.loads(socket.recv())
                if message.get("type") == "ping":
                    socket.send(json.dumps({"id": message.get("id"), "type": "pong"}))
                    continue
                event = message.get("event") or {}
                data = event.get("data") or {}
                new_state = data.get("new_state")
                if new_state and new_state.get("entity_id") in self.entity_ids:
                    self._store(new_state, notify=True)
        finally:
            self._socket = None
            socket.close()

    def _store(self, raw, notify):
        state = EntityState.from_message(raw, monotonic=self._clock())
        with self._lock:
            previous = self._states.get(state.entity_id)
            # Preserve the last meaningful value while marking it unavailable.
            if not state.available and previous and previous.available:
                state = replace(
                    previous,
                    available=False,
                    received_monotonic=state.received_monotonic,
                )
            self._states[state.entity_id] = state
        if notify:
            for listener in tuple(self._listeners):
                try:
                    listener(state.entity_id, previous, state)
                except Exception:
                    logger.exception("Home Assistant state listener failed")
