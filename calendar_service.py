"""Read and normalize upcoming events from iCalendar sources."""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

import requests
from ical.calendar_stream import IcsCalendarStream

logger = logging.getLogger(__name__)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _split_sources(value: str) -> List[str]:
    return [
        item.strip() for item in value.replace("\n", ",").split(",") if item.strip()
    ]


@dataclass(frozen=True)
class CalendarEvent:
    uid: str
    summary: str
    start: datetime
    end: datetime
    location: str = ""
    all_day: bool = False
    stale: bool = False


def _as_datetime(value, timezone: ZoneInfo) -> tuple[datetime, bool]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone)
        return value.astimezone(timezone), False
    if isinstance(value, date):
        return datetime.combine(value, datetime_time.min, timezone), True
    raise ValueError(f"unsupported calendar date value: {value!r}")


def parse_ics_events(
    payload: str,
    range_start: datetime,
    range_end: datetime,
    *,
    timezone: ZoneInfo,
    include_all_day: bool,
    show_details: bool,
    stale: bool = False,
) -> List[CalendarEvent]:
    """Expand and normalize events in an ICS payload for a bounded range."""

    calendar = IcsCalendarStream.calendar_from_ics(payload)
    events = []
    for item in calendar.timeline.overlapping(range_start, range_end):
        status = getattr(item.status, "value", item.status)
        if str(status or "").upper() == "CANCELLED":
            continue
        start, all_day = _as_datetime(item.start, timezone)
        end, _ = _as_datetime(item.end or item.start, timezone)
        if (all_day and end <= range_start) or (not all_day and start < range_start):
            continue
        if start >= range_end:
            continue
        if all_day and not include_all_day:
            continue
        summary = str(item.summary or "Untitled event") if show_details else "Busy"
        location = str(item.location or "") if show_details else ""
        events.append(
            CalendarEvent(
                uid=f"{item.uid or 'event'}:{start.isoformat()}",
                summary=summary,
                start=start,
                end=end,
                location=location,
                all_day=all_day,
                stale=stale,
            )
        )
    return sorted(events, key=lambda event: (event.start, event.end, event.summary))


class IcsCalendarSource:
    """Fetch one HTTP or file ICS source with a private last-good cache."""

    def __init__(
        self,
        locator: str,
        *,
        source_type: str,
        cache_dir: Path,
        timeout: float,
        max_stale_seconds: int,
        session=None,
    ):
        if source_type not in {"ics", "file"}:
            raise ValueError(f"unsupported calendar source: {source_type}")
        self.locator = locator
        self.source_type = source_type
        self.timeout = timeout
        self.max_stale_seconds = max_stale_seconds
        self.session = session or requests.Session()
        digest = hashlib.sha256(locator.encode("utf-8")).hexdigest()[:16]
        self.label = f"{source_type}-{digest}"
        self.cache_file = cache_dir / f"calendar-{digest}.ics"
        self._etag = None
        self._last_modified = None
        self._payload = None
        self._pending_etag = None
        self._pending_last_modified = None

    def events_between(
        self,
        range_start: datetime,
        range_end: datetime,
        *,
        timezone: ZoneInfo,
        include_all_day: bool,
        show_details: bool,
    ) -> List[CalendarEvent]:
        try:
            payload = self._read_payload()
            stale = False
        except Exception as exc:
            logger.warning(
                "Calendar source %s unavailable (%s)",
                self.label,
                type(exc).__name__,
            )
            payload = self._read_cache()
            stale = True
        if payload is None:
            return []
        try:
            events = parse_ics_events(
                payload,
                range_start,
                range_end,
                timezone=timezone,
                include_all_day=include_all_day,
                show_details=show_details,
                stale=stale,
            )
        except Exception as exc:
            logger.warning(
                "Calendar source %s could not be parsed (%s)",
                self.label,
                type(exc).__name__,
            )
            if not stale:
                cached = self._read_cache()
                if cached is not None and cached != payload:
                    try:
                        return parse_ics_events(
                            cached,
                            range_start,
                            range_end,
                            timezone=timezone,
                            include_all_day=include_all_day,
                            show_details=show_details,
                            stale=True,
                        )
                    except Exception:
                        pass
            return []
        if not stale and self.source_type == "ics":
            self._payload = payload
            self._etag = self._pending_etag or self._etag
            self._last_modified = self._pending_last_modified or self._last_modified
            self._write_cache(payload)
        return events

    def _read_payload(self) -> str:
        if self.source_type == "file":
            return Path(self.locator).expanduser().read_text(encoding="utf-8")

        headers = {
            "Accept": "text/calendar",
            "User-Agent": "rpi-waiting-time-display/1",
        }
        if self._etag:
            headers["If-None-Match"] = self._etag
        if self._last_modified:
            headers["If-Modified-Since"] = self._last_modified
        response = self.session.get(
            self.locator,
            headers=headers,
            timeout=self.timeout,
        )
        if response.status_code == 304:
            self._pending_etag = None
            self._pending_last_modified = None
            payload = self._payload or self._read_cache(ignore_age=True)
            if payload is None:
                raise ValueError("calendar source returned 304 without cached data")
            return payload
        response.raise_for_status()
        payload = response.text
        self._pending_etag = response.headers.get("ETag")
        self._pending_last_modified = response.headers.get("Last-Modified")
        return payload

    def _write_cache(self, payload: str) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_file.with_suffix(".tmp")
            temporary.write_text(payload, encoding="utf-8")
            temporary.chmod(0o600)
            temporary.replace(self.cache_file)
        except OSError as exc:
            logger.warning(
                "Could not persist calendar cache %s (%s)",
                self.label,
                type(exc).__name__,
            )

    def _read_cache(self, *, ignore_age: bool = False) -> Optional[str]:
        try:
            age = time.time() - self.cache_file.stat().st_mtime
            if not ignore_age and age > self.max_stale_seconds:
                return None
            return self.cache_file.read_text(encoding="utf-8")
        except OSError:
            return None


class CalendarClient:
    """Combine configured sources and cache a normalized upcoming event list."""

    def __init__(self, sources: Optional[Iterable[IcsCalendarSource]] = None):
        self.enabled = _enabled("calendar_enabled")
        timezone_name = os.getenv("calendar_timezone", "Europe/Brussels").strip()
        try:
            self.timezone = ZoneInfo(timezone_name)
        except (KeyError, ValueError):
            logger.error("Unknown calendar_timezone %s; using UTC", timezone_name)
            self.timezone = ZoneInfo("UTC")
        self.refresh_interval = max(
            30, int(os.getenv("calendar_refresh_interval", "300"))
        )
        self.lookahead_days = max(1, int(os.getenv("calendar_lookahead_days", "3")))
        self.include_all_day = _enabled("calendar_include_all_day")
        self.show_details = _enabled("calendar_show_details", "true")
        self._sources = (
            list(sources) if sources is not None else self._configured_sources()
        )
        self._events: List[CalendarEvent] = []
        self._last_fetch_monotonic = 0.0
        self._lock = threading.Lock()

    def _configured_sources(self) -> List[IcsCalendarSource]:
        source_type = os.getenv("calendar_source", "ics").strip().lower()
        if source_type == "file":
            value = os.getenv("calendar_ics_files", os.getenv("calendar_ics_file", ""))
        else:
            value = os.getenv("calendar_ics_urls", os.getenv("calendar_ics_url", ""))
        locators = _split_sources(value)
        if self.enabled and not locators:
            logger.error(
                "Calendar display enabled but no %s sources configured", source_type
            )
        cache_dir = Path(os.getenv("calendar_cache_dir", "cache")).expanduser()
        try:
            timeout = float(os.getenv("calendar_timeout", "10"))
            max_stale = int(os.getenv("calendar_max_stale_seconds", "21600"))
            return [
                IcsCalendarSource(
                    locator,
                    source_type=source_type,
                    cache_dir=cache_dir,
                    timeout=timeout,
                    max_stale_seconds=max_stale,
                )
                for locator in locators
            ]
        except ValueError as exc:
            logger.error("Invalid calendar configuration: %s", exc)
            return []

    def get_events(self, now: Optional[datetime] = None, *, force: bool = False):
        if not self.enabled:
            return []
        now = (now or datetime.now(self.timezone)).astimezone(self.timezone)
        monotonic_now = time.monotonic()
        with self._lock:
            if (
                force
                or not self._last_fetch_monotonic
                or monotonic_now - self._last_fetch_monotonic >= self.refresh_interval
            ):
                range_end = now + timedelta(days=self.lookahead_days)
                fetched = []
                for source in self._sources:
                    fetched.extend(
                        source.events_between(
                            now,
                            range_end,
                            timezone=self.timezone,
                            include_all_day=self.include_all_day,
                            show_details=self.show_details,
                        )
                    )
                unique = {}
                for event in fetched:
                    key = (event.uid, event.start)
                    existing = unique.get(key)
                    if existing is None or (existing.stale and not event.stale):
                        unique[key] = event
                self._events = sorted(
                    unique.values(), key=lambda event: (event.start, event.summary)
                )
                self._last_fetch_monotonic = monotonic_now
            return [
                replace(event)
                for event in self._events
                if (event.all_day and event.end > now)
                or (not event.all_day and event.start >= now)
            ]
