"""Read and normalize upcoming events from iCalendar sources."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from ical.calendar_stream import IcsCalendarStream

logger = logging.getLogger(__name__)
logging.getLogger("ical").setLevel(logging.WARNING)

GOOGLE_CALENDAR_READONLY_SCOPE = (
    "https://www.googleapis.com/auth/calendar.events.readonly"
)


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
    """Fetch one HTTP or file ICS source with a private last-good cache.

    HTTP ICS is a legacy compatibility path: the response and calendar model are
    inherently unbounded. Prefer GoogleCalendarApiSource on memory-limited hosts.
    """

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


class GoogleCalendarApiSource:
    """Read a strictly bounded window from Google Calendar's Events API."""

    def __init__(
        self,
        calendar_id: str,
        *,
        credentials_file: Path,
        cache_dir: Path,
        timeout: float,
        max_stale_seconds: int,
        max_events: int = 100,
        delegated_user: str = "",
        session=None,
        credentials=None,
    ):
        if not calendar_id:
            raise ValueError("calendar_google_calendar_id is required")
        if max_events < 1:
            raise ValueError("calendar_google_max_events must be positive")
        self.calendar_id = calendar_id
        self.timeout = timeout
        self.max_stale_seconds = max_stale_seconds
        self.max_events = max_events
        self.session = session or requests.Session()
        self.label = (
            "google-api-" + hashlib.sha256(calendar_id.encode("utf-8")).hexdigest()[:16]
        )
        self.cache_file = cache_dir / f"calendar-{self.label}.json"
        if credentials is None:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_file), scopes=[GOOGLE_CALENDAR_READONLY_SCOPE]
            )
            if delegated_user:
                credentials = credentials.with_subject(delegated_user)
        self.credentials = credentials

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
            raw_events = self._fetch(range_start, range_end, timezone)
            events = self._normalize(
                raw_events,
                range_start,
                range_end,
                timezone,
                include_all_day,
                show_details,
                stale=False,
            )
            self._write_cache(raw_events)
            return events
        except Exception as exc:
            logger.warning(
                "Calendar source %s unavailable (%s)", self.label, type(exc).__name__
            )
            cached = self._read_cache()
            if cached is None:
                return []
            return self._normalize(
                cached,
                range_start,
                range_end,
                timezone,
                include_all_day,
                show_details,
                stale=True,
            )

    def _fetch(self, range_start, range_end, timezone):
        if not getattr(self.credentials, "valid", False):
            from google.auth.transport.requests import Request as GoogleAuthRequest

            self.credentials.refresh(GoogleAuthRequest(session=self.session))
        url = (
            "https://www.googleapis.com/calendar/v3/calendars/"
            f"{quote(self.calendar_id, safe='')}/events"
        )
        params = {
            "timeMin": range_start.isoformat(),
            "timeMax": range_end.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "timeZone": str(timezone),
            "maxResults": min(self.max_events, 2500),
            "fields": (
                "items(id,iCalUID,status,summary,location,start,end),nextPageToken"
            ),
        }
        headers = {
            "Authorization": f"Bearer {self.credentials.token}",
            "Accept": "application/json",
            "User-Agent": "rpi-waiting-time-display/1",
        }
        items = []
        while len(items) < self.max_events:
            response = self.session.get(
                url, params=params, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            page = response.json()
            page_items = page.get("items", [])
            if not isinstance(page_items, list):
                raise ValueError("Google Calendar returned invalid items")
            items.extend(page_items[: self.max_events - len(items)])
            page_token = page.get("nextPageToken")
            if not page_token or len(items) >= self.max_events:
                break
            params["pageToken"] = page_token
            params["maxResults"] = min(self.max_events - len(items), 2500)
        return items

    @staticmethod
    def _normalize(
        items,
        range_start,
        range_end,
        timezone,
        include_all_day,
        show_details,
        *,
        stale,
    ):
        events = []
        for item in items:
            if item.get("status", "confirmed").upper() == "CANCELLED":
                continue
            start, all_day = GoogleCalendarApiSource._api_datetime(
                item.get("start", {}), timezone
            )
            end, _ = GoogleCalendarApiSource._api_datetime(
                item.get("end") or item.get("start", {}), timezone
            )
            if (all_day and end <= range_start) or (
                not all_day and start < range_start
            ):
                continue
            if start >= range_end or (all_day and not include_all_day):
                continue
            identity = item.get("iCalUID") or item.get("id") or "event"
            events.append(
                CalendarEvent(
                    uid=f"{identity}:{start.isoformat()}",
                    summary=(
                        str(item.get("summary") or "Untitled event")
                        if show_details
                        else "Busy"
                    ),
                    start=start,
                    end=end,
                    location=str(item.get("location") or "") if show_details else "",
                    all_day=all_day,
                    stale=stale,
                )
            )
        return sorted(events, key=lambda event: (event.start, event.end, event.summary))

    @staticmethod
    def _api_datetime(value, timezone):
        if value.get("dateTime"):
            parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone)
            return parsed.astimezone(timezone), False
        if value.get("date"):
            return (
                datetime.combine(
                    date.fromisoformat(value["date"]), datetime_time.min, timezone
                ),
                True,
            )
        raise ValueError("Google Calendar event has no start/end date")

    def _write_cache(self, items):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(items, separators=(",", ":")), "utf-8")
            temporary.chmod(0o600)
            temporary.replace(self.cache_file)
        except OSError as exc:
            logger.warning(
                "Could not persist calendar cache %s (%s)",
                self.label,
                type(exc).__name__,
            )

    def _read_cache(self):
        try:
            if time.time() - self.cache_file.stat().st_mtime > self.max_stale_seconds:
                return None
            data = json.loads(self.cache_file.read_text("utf-8"))
            return data if isinstance(data, list) else None
        except (OSError, ValueError):
            return None


class CalendarClient:
    """Combine configured sources and cache a normalized upcoming event list."""

    def __init__(self, sources: Optional[Iterable[object]] = None):
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

    def _configured_sources(self) -> List[object]:
        source_type = os.getenv("calendar_source", "ics").strip().lower()
        cache_dir = Path(os.getenv("calendar_cache_dir", "cache")).expanduser()
        try:
            timeout = float(os.getenv("calendar_timeout", "10"))
            max_stale = int(os.getenv("calendar_max_stale_seconds", "21600"))
            if source_type == "google_api":
                credentials_value = os.getenv(
                    "calendar_google_credentials_file", ""
                ).strip()
                calendar_ids = _split_sources(
                    os.getenv(
                        "calendar_google_calendar_ids",
                        os.getenv("calendar_google_calendar_id", ""),
                    )
                )
                if self.enabled and (not calendar_ids or not credentials_value):
                    logger.error(
                        "Calendar display enabled but Google API configuration is incomplete"
                    )
                    return []
                if not calendar_ids:
                    return []
                credentials_file = Path(credentials_value).expanduser()
                max_events = int(os.getenv("calendar_google_max_events", "100"))
                delegated_user = os.getenv("calendar_google_delegated_user", "").strip()
                return [
                    GoogleCalendarApiSource(
                        calendar_id,
                        credentials_file=credentials_file,
                        cache_dir=cache_dir,
                        timeout=timeout,
                        max_stale_seconds=max_stale,
                        max_events=max_events,
                        delegated_user=delegated_user,
                    )
                    for calendar_id in calendar_ids
                ]
            if source_type == "file":
                value = os.getenv(
                    "calendar_ics_files", os.getenv("calendar_ics_file", "")
                )
            elif source_type == "ics":
                value = os.getenv(
                    "calendar_ics_urls", os.getenv("calendar_ics_url", "")
                )
            else:
                raise ValueError(f"unsupported calendar source: {source_type}")
            locators = _split_sources(value)
            if self.enabled and not locators:
                logger.error(
                    "Calendar display enabled but no %s sources configured", source_type
                )
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
        except (ImportError, OSError, ValueError) as exc:
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
