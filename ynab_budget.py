"""Read-only YNAB current-month snapshot for glanceable display views."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def _enabled(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() == "true"


def _money(value: Any) -> float:
    return float(value or 0) / 1000


@dataclass(frozen=True)
class YnabCategory:
    name: str
    group: str
    assigned: float
    activity: float
    available: float

    @property
    def spent(self) -> float:
        return max(0.0, -self.activity)

    @property
    def assigned_remaining(self) -> float:
        """Current-month assignment left after outflows, excluding rollover."""
        return max(0.0, self.assigned - self.spent)


@dataclass
class YnabSnapshot:
    generated_at: str
    month: str
    currency_symbol: str
    categories: List[YnabCategory]
    stale: bool = False

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "YnabSnapshot":
        categories = [
            YnabCategory(
                name=str(item.get("name") or "Unnamed"),
                group=str(item.get("group") or "Other"),
                assigned=float(item.get("assigned", 0)),
                activity=float(item.get("activity", 0)),
                available=float(item.get("available", 0)),
            )
            for item in payload.get("categories", [])
            if isinstance(item, dict)
        ]
        return cls(
            generated_at=str(payload.get("generated_at") or ""),
            month=str(payload.get("month") or ""),
            currency_symbol=str(payload.get("currency_symbol") or "€"),
            categories=categories,
        )

    def category(self, name: str) -> Optional[YnabCategory]:
        wanted = name.strip().casefold()
        return next(
            (
                item
                for item in self.categories
                if item.name.casefold() == wanted
            ),
            None,
        )

    def selected(self, names: List[str]) -> List[YnabCategory]:
        return [
            item for name in names if (item := self.category(name)) is not None
        ]


class YnabBudgetClient:
    """Fetch the current month and keep a privacy-safe local cache."""

    API_BASE = "https://api.ynab.com/v1"

    def __init__(self):
        self.enabled = _enabled("ynab_enabled")
        self.access_token = os.getenv("ynab_access_token", "").strip()
        self.budget_id = (
            os.getenv("ynab_budget_id", "last-used").strip() or "last-used"
        )
        self.timeout = float(os.getenv("ynab_timeout", "8"))
        self.refresh_interval = int(os.getenv("ynab_refresh_interval", "900"))
        self.max_stale_seconds = int(
            os.getenv("ynab_max_stale_seconds", "21600")
        )
        self.cache_file = Path(
            os.getenv("ynab_cache_file", "cache/ynab_last_good.json")
        )
        self._snapshot: Optional[YnabSnapshot] = None
        self._last_fetch_monotonic = 0.0
        self._lock = threading.Lock()
        self._fetch_lock = threading.Lock()

    def _request(self) -> Dict[str, Any]:
        if not self.access_token:
            raise ValueError("ynab_access_token is empty")
        url = f"{self.API_BASE}/budgets/{self.budget_id}/months/current"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.access_token}",
                "User-Agent": "rpi-waiting-time-display/1",
            },
        )
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)

    @staticmethod
    def _normalize(payload: Dict[str, Any]) -> Dict[str, Any]:
        month = (payload.get("data") or {}).get("month") or {}
        categories = []
        for item in month.get("categories", []):
            if item.get("deleted") or item.get("hidden"):
                continue
            categories.append(
                {
                    "name": item.get("name") or "Unnamed",
                    "group": item.get("category_group_name") or "Other",
                    "assigned": _money(item.get("budgeted")),
                    "activity": _money(item.get("activity")),
                    "available": _money(item.get("balance")),
                }
            )
        currency = os.getenv("ynab_currency_symbol", "€").strip() or "€"
        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "month": month.get("month")
            or date.today().replace(day=1).isoformat(),
            "currency_symbol": currency,
            "categories": categories,
        }

    def _write_cache(self, payload: Dict[str, Any]) -> None:
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload), encoding="utf-8")
            temporary.replace(self.cache_file)
        except OSError as exc:
            logger.warning("Could not persist YNAB cache: %s", exc)

    def _load_stale(self) -> Optional[YnabSnapshot]:
        try:
            if (
                time.time() - self.cache_file.stat().st_mtime
                > self.max_stale_seconds
            ):
                return None
            snapshot = YnabSnapshot.from_dict(
                json.loads(self.cache_file.read_text())
            )
            snapshot.stale = True
            return snapshot
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def get_snapshot(self, force: bool = False) -> Optional[YnabSnapshot]:
        if not self.enabled:
            return None
        if (
            not force
            and self._last_fetch_monotonic
            and time.monotonic() - self._last_fetch_monotonic
            < self.refresh_interval
        ):
            return self._snapshot
        with self._fetch_lock:
            if (
                not force
                and self._last_fetch_monotonic
                and time.monotonic() - self._last_fetch_monotonic
                < self.refresh_interval
            ):
                return self._snapshot
            try:
                normalized = self._normalize(self._request())
                self._write_cache(normalized)
                snapshot = YnabSnapshot.from_dict(normalized)
            except Exception as exc:
                # HTTP errors can include the private budget URL. Log only the
                # exception type and keep identifiers out of service logs.
                logger.warning(
                    "YNAB refresh failed (%s); using cache", type(exc).__name__
                )
                snapshot = self._load_stale()
            with self._lock:
                self._snapshot = snapshot
                self._last_fetch_monotonic = time.monotonic()
            return snapshot


def configured_views() -> List[str]:
    allowed = {"month", "daily", "active", "funding", "exception"}
    views = [
        item.strip().lower()
        for item in os.getenv(
            "ynab_views", "month,daily,active,funding,exception"
        ).split(",")
        if item.strip().lower() in allowed
    ]
    return views or ["month"]


def view_at(current_time: datetime, views: List[str]) -> str:
    duration = max(1, int(os.getenv("ynab_view_duration", "120")))
    return views[int(current_time.timestamp()) // duration % len(views)]
