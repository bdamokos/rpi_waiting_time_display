"""Thread-safe ownership arbitration for display plugins.

The normal scheduled display is the implicit base layer. Optional plugins claim
the screen for a bounded amount of time and may be pre-empted by a higher
priority claim. An exclusive winning claim stays in control until it is
released or expires, which gives urgent screens a safe lock without allowing a
plugin failure to hold the display forever.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScreenClaim:
    owner: str
    priority: int
    expires_at: float
    exclusive: bool = False
    sequence: int = 0


class ScreenArbiter:
    """Choose which optional display plugin currently owns the screen."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._claims: Dict[str, ScreenClaim] = {}
        self._current_owner: Optional[str] = None
        self._sequence = 0
        self._lock = threading.RLock()

    def claim(
        self,
        owner: str,
        priority: int,
        ttl_seconds: float,
        *,
        exclusive: bool = False,
    ) -> bool:
        """Create or refresh a claim and return whether it is active."""

        owner = owner.strip()
        if not owner:
            raise ValueError("screen claim owner must not be empty")
        if ttl_seconds <= 0:
            raise ValueError("screen claim ttl_seconds must be positive")

        with self._lock:
            self._prune_expired()
            existing = self._claims.get(owner)
            if existing:
                sequence = existing.sequence
            else:
                self._sequence += 1
                sequence = self._sequence
            self._claims[owner] = ScreenClaim(
                owner=owner,
                priority=int(priority),
                expires_at=self._clock() + float(ttl_seconds),
                exclusive=exclusive,
                sequence=sequence,
            )
            previous = self._current_owner
            self._select_owner()
            self._log_transition(previous)
            return self._current_owner == owner

    def release(self, owner: str) -> bool:
        """Remove a claim and return whether its owner controlled the screen."""

        with self._lock:
            self._prune_expired()
            was_active = self._current_owner == owner
            previous = self._current_owner
            self._claims.pop(owner, None)
            if was_active:
                self._current_owner = None
            self._select_owner()
            self._log_transition(previous)
            return was_active

    def active_owner(self) -> Optional[str]:
        """Return the active plugin owner, or ``None`` for the base display."""

        with self._lock:
            previous = self._current_owner
            self._prune_expired()
            self._select_owner()
            self._log_transition(previous)
            return self._current_owner

    def can_render(self, owner: Optional[str] = None) -> bool:
        """Return whether an owner may render; ``None`` means the base layer."""

        return self.active_owner() == owner

    def has_claim(self, owner: str) -> bool:
        with self._lock:
            self._prune_expired()
            return owner in self._claims

    def claim_for(self, owner: str) -> Optional[ScreenClaim]:
        with self._lock:
            self._prune_expired()
            return self._claims.get(owner)

    def _prune_expired(self) -> None:
        now = self._clock()
        expired = [
            owner for owner, claim in self._claims.items() if claim.expires_at <= now
        ]
        for owner in expired:
            self._claims.pop(owner, None)
            if self._current_owner == owner:
                self._current_owner = None

    def _select_owner(self) -> None:
        current = self._claims.get(self._current_owner or "")
        if current and current.exclusive:
            return
        if not self._claims:
            self._current_owner = None
            return
        # Existing ownership wins an equal-priority tie. Otherwise the older
        # claim wins, preventing same-priority plugins from flickering.
        self._current_owner = min(
            self._claims.values(),
            key=lambda claim: (
                -claim.priority,
                0 if claim.owner == self._current_owner else 1,
                claim.sequence,
            ),
        ).owner

    def _log_transition(self, previous: Optional[str]) -> None:
        if previous != self._current_owner:
            logger.info(
                "Screen ownership changed: %s -> %s",
                previous or "base",
                self._current_owner or "base",
            )
