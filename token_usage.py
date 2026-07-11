"""Configurable schedule and data client for token-usage display modes."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _minutes(value: str) -> int:
    hour, minute = value.strip().split(":", 1)
    parsed = int(hour) * 60 + int(minute)
    if parsed < 0 or parsed > 24 * 60 or int(minute) not in range(60):
        raise ValueError(f"invalid time: {value}")
    return parsed % (24 * 60)


WEEKDAYS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def _weekday_set(value: str) -> FrozenSet[int]:
    """Parse a schedule day selector such as ``weekdays`` or ``mon+wed-fri``."""

    selector = value.strip().lower()
    aliases = {
        "daily": frozenset(range(7)),
        "all": frozenset(range(7)),
        "weekdays": frozenset(range(5)),
        "weekends": frozenset({5, 6}),
    }
    if selector in aliases:
        return aliases[selector]

    selected = set()
    for part in selector.split("+"):
        names = part.strip().split("-")
        if len(names) == 1 and names[0] in WEEKDAYS:
            selected.add(WEEKDAYS[names[0]])
            continue
        if len(names) != 2 or any(name not in WEEKDAYS for name in names):
            raise ValueError(f"invalid day selector: {value}")
        start, end = (WEEKDAYS[name] for name in names)
        selected.update((start + offset) % 7 for offset in range((end - start) % 7 + 1))
    if not selected:
        raise ValueError(f"invalid day selector: {value}")
    return frozenset(selected)


@dataclass(frozen=True)
class ScheduleEntry:
    mode: str
    start_minute: int
    end_minute: int
    weekdays: FrozenSet[int] = frozenset(range(7))

    def contains(self, value: datetime) -> bool:
        if value.weekday() not in self.weekdays:
            return False
        minute = value.hour * 60 + value.minute
        if self.start_minute == self.end_minute:
            return True
        if self.start_minute < self.end_minute:
            return self.start_minute <= minute < self.end_minute
        return minute >= self.start_minute or minute < self.end_minute


class DisplaySchedule:
    """Parse time-only or weekday-aware entries and select the current mode.

    Entries use ``mode@HH:MM-HH:MM`` or
    ``mode@DAYS@HH:MM-HH:MM``. Earlier entries have priority.
    """

    ALLOWED_MODES = {"auto", "transit", "weather", "token", "token-always"}

    def __init__(self, value: str):
        self.entries: List[ScheduleEntry] = []
        for raw_entry in filter(None, (part.strip() for part in value.split(","))):
            try:
                parts = raw_entry.split("@")
                if len(parts) == 2:
                    mode, window = parts
                    weekdays = frozenset(range(7))
                elif len(parts) == 3:
                    mode, days, window = parts
                    weekdays = _weekday_set(days)
                else:
                    raise ValueError("expected mode@time or mode@days@time")
                start, end = window.split("-", 1)
                mode = mode.strip().lower()
                if mode not in self.ALLOWED_MODES:
                    raise ValueError(f"unsupported mode: {mode}")
                self.entries.append(
                    ScheduleEntry(mode, _minutes(start), _minutes(end), weekdays)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid display_schedule entry '{raw_entry}': {exc}"
                ) from exc

    def mode_at(self, value: datetime) -> str:
        for entry in self.entries:
            if entry.contains(value):
                return entry.mode
        return "auto"


@dataclass
class RateWindow:
    used_percent: float
    resets_at: Optional[str] = None

    @property
    def remaining_percent(self) -> float:
        return max(0.0, min(100.0, 100.0 - self.used_percent))


@dataclass
class DailyUsage:
    date: str
    cost_usd: float
    total_tokens: int


@dataclass
class TokenUsageSnapshot:
    generated_at: str
    primary: RateWindow
    secondary: RateWindow
    daily: List[DailyUsage]
    month_cost_usd: float
    month_tokens: int
    resets_available: int = 0
    active: bool = False
    currency: str = "USD"
    stale: bool = False

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "TokenUsageSnapshot":
        limits = payload.get("limits") or {}
        primary = limits.get("primary") or {}
        secondary = limits.get("secondary") or {}
        daily = [
            DailyUsage(
                date=str(item["date"]),
                cost_usd=float(item.get("cost_usd", 0)),
                total_tokens=int(item.get("total_tokens", 0)),
            )
            for item in payload.get("daily", [])
            if isinstance(item, dict) and item.get("date")
        ]
        month = payload.get("month_to_date") or {}
        try:
            resets_available = max(0, int(limits.get("resets_available", 0)))
        except (TypeError, ValueError):
            resets_available = 0
        return cls(
            generated_at=str(payload.get("generated_at") or ""),
            primary=RateWindow(
                float(primary.get("used_percent", 0)), primary.get("resets_at")
            ),
            secondary=RateWindow(
                float(secondary.get("used_percent", 0)), secondary.get("resets_at")
            ),
            daily=daily,
            month_cost_usd=float(
                month.get("cost_usd", sum(day.cost_usd for day in daily))
            ),
            month_tokens=int(
                month.get("total_tokens", sum(day.total_tokens for day in daily))
            ),
            resets_available=resets_available,
            # Missing activity information fails closed: token views are only
            # eligible when the source explicitly reports current activity.
            active=payload.get("active") is True,
            currency=str(payload.get("currency") or "USD"),
        )


class TokenUsageClient:
    """Read normalized usage JSON from HTTP or a file with last-good caching."""

    def __init__(self):
        self.enabled = _enabled("token_usage_enabled")
        self.source = os.getenv("token_usage_source", "http").strip().lower()
        self.url = os.getenv("token_usage_url", "").strip()
        self.file = Path(
            os.getenv("token_usage_file", "cache/token_usage.json")
        ).expanduser()
        self.auth_token = os.getenv("token_usage_auth_token", "").strip()
        self.timeout = float(os.getenv("token_usage_timeout", "5"))
        self.refresh_interval = int(os.getenv("token_usage_refresh_interval", "300"))
        self.max_stale_seconds = int(
            os.getenv("token_usage_max_stale_seconds", "21600")
        )
        self.cache_file = Path(
            os.getenv("token_usage_cache_file", "cache/token_usage_last_good.json")
        )
        self._snapshot: Optional[TokenUsageSnapshot] = None
        self._last_fetch_monotonic = 0.0

    def _read_payload(self) -> Dict[str, Any]:
        if self.source == "file":
            with self.file.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        if self.source != "http":
            raise ValueError(f"unsupported token_usage_source: {self.source}")
        if not self.url:
            raise ValueError("token_usage_url is empty")
        headers = {
            "Accept": "application/json",
            "User-Agent": "rpi-waiting-time-display/1",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        request = Request(self.url, headers=headers)
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    def _write_cache(self, payload: Dict[str, Any]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.replace(self.cache_file)
        except OSError as exc:
            logger.warning("Could not persist token usage cache: %s", exc)

    def _load_stale_cache(self) -> Optional[TokenUsageSnapshot]:
        try:
            age = time.time() - self.cache_file.stat().st_mtime
            if age > self.max_stale_seconds:
                return None
            payload = json.loads(self.cache_file.read_text(encoding="utf-8"))
            snapshot = TokenUsageSnapshot.from_dict(payload)
            # A cached response can preserve usage totals, but it cannot prove
            # that Codex is still active while the source is unavailable.
            snapshot.active = False
            snapshot.stale = True
            return snapshot
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def get_snapshot(self, force: bool = False) -> Optional[TokenUsageSnapshot]:
        if not self.enabled:
            return None
        now = time.monotonic()
        if (
            self._snapshot
            and not force
            and now - self._last_fetch_monotonic < self.refresh_interval
        ):
            return self._snapshot
        self._last_fetch_monotonic = now
        try:
            payload = self._read_payload()
            self._snapshot = TokenUsageSnapshot.from_dict(payload)
            self._write_cache(payload)
        except Exception as exc:
            logger.warning("Token usage source unavailable: %s", exc)
            # Reload from disk even when an in-memory value exists so the
            # configured maximum stale age is always enforced.
            self._snapshot = self._load_stale_cache()
            if self._snapshot:
                self._snapshot.stale = True
        return self._snapshot


def configured_schedule() -> DisplaySchedule:
    value = os.getenv(
        "display_schedule",
        "transit@06:00-10:00,token@10:00-22:00,weather@22:00-06:00",
    )
    try:
        return DisplaySchedule(value)
    except ValueError as exc:
        logger.error("%s; falling back to automatic display selection", exc)
        return DisplaySchedule("")


def configured_token_views() -> List[str]:
    allowed = {"month", "limits"}
    views = [
        part.strip().lower()
        for part in os.getenv("token_usage_views", "month,limits").split(",")
    ]
    return [view for view in views if view in allowed] or ["limits"]


def token_view_at(value: datetime, views: List[str]) -> str:
    duration = max(60, int(os.getenv("token_usage_view_duration", "300")))
    return views[int(value.timestamp()) // duration % len(views)]
