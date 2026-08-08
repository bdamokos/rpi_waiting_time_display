"""Date-bounded privacy policy for suppressing configured display modules."""

from __future__ import annotations

import fnmatch
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)


def _enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class DateWindow:
    start: date
    end: date

    def contains(self, value: date) -> bool:
        return self.start <= value <= self.end


def _parse_windows(value: str) -> Tuple[DateWindow, ...]:
    windows = []
    for raw_entry in value.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if ".." in entry:
            raw_start, raw_end = entry.split("..", 1)
        else:
            raw_start = raw_end = entry
        start = date.fromisoformat(raw_start.strip())
        end = date.fromisoformat(raw_end.strip())
        if end < start:
            raise ValueError(f"vacation date range ends before it starts: {entry}")
        windows.append(DateWindow(start, end))
    return tuple(windows)


class VacationPrivacyMode:
    """Suppress sensitive display names during configured local-date windows.

    Empty blackout dates mean that the enabled switch is a manual always-on
    privacy mode. Invalid dates or timezone names fail closed by activating the
    policy continuously, while still allowing non-sensitive displays to run.
    """

    def __init__(
        self,
        *,
        enabled: bool = False,
        sensitive_displays: Iterable[str] = (),
        windows: Iterable[DateWindow] = (),
        timezone: str = "UTC",
        fallback_mode: str = "transit",
        fail_closed: bool = False,
    ):
        self.enabled = bool(enabled)
        self.sensitive_displays = tuple(
            item.strip().lower() for item in sensitive_displays if item.strip()
        )
        self.windows = tuple(windows)
        self.fail_closed = bool(fail_closed)
        self.timezone_name = timezone
        self.timezone = ZoneInfo(timezone)
        self.fallback_mode = fallback_mode.strip().lower()

    @classmethod
    def from_env(cls) -> "VacationPrivacyMode":
        enabled = _enabled(os.getenv("vacation_mode_enabled", "false"))
        displays = os.getenv("vacation_mode_sensitive_displays", "").split(",")
        timezone = os.getenv("vacation_mode_timezone", "UTC").strip() or "UTC"
        fallback = os.getenv("vacation_mode_fallback_mode", "transit")
        try:
            windows = _parse_windows(os.getenv("vacation_mode_blackout_dates", ""))
            return cls(
                enabled=enabled,
                sensitive_displays=displays,
                windows=windows,
                timezone=timezone,
                fallback_mode=fallback,
            )
        except (ValueError, ZoneInfoNotFoundError) as exc:
            logger.error(
                "Invalid vacation privacy configuration; sensitive displays "
                "will remain suppressed until corrected: %s",
                exc,
            )
            return cls(
                enabled=enabled,
                sensitive_displays=displays,
                timezone="UTC",
                fallback_mode=fallback,
                fail_closed=enabled,
            )

    def is_active(self, now: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        if self.fail_closed or not self.windows:
            return True
        moment = now if now is not None else datetime.now(timezone.utc)
        if moment.tzinfo is None:
            raise ValueError("vacation privacy timestamps must be timezone-aware")
        local_date = moment.astimezone(self.timezone).date()
        return any(window.contains(local_date) for window in self.windows)

    def blocks(self, display_name: str, now: Optional[datetime] = None) -> bool:
        if not self.is_active(now):
            return False
        name = (display_name or "").strip().lower()
        if not name:
            return False
        return any(self._matches(pattern, name) for pattern in self.sensitive_displays)

    @staticmethod
    def _matches(pattern: str, name: str) -> bool:
        if any(character in pattern for character in "*?["):
            return fnmatch.fnmatchcase(name, pattern)
        return name == pattern or name.startswith(
            (f"{pattern}-", f"{pattern}_", f"{pattern}:")
        )

    def safe_fallback(self, now: Optional[datetime] = None) -> Optional[str]:
        configured = self.fallback_mode
        candidates = [configured, "transit", "weather", "auto"]
        for candidate in candidates:
            if candidate in {"auto", "transit", "weather"} and not self.blocks(
                candidate, now
            ):
                return candidate
        return None
