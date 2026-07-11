# flake8: noqa: E501
"""Baseline-first breaking-news feed watcher with bounded persistent state."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlsplit

import requests

from rss_service import FeedEntry, FeedSource, env_int, parse_feed

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = (
    "breaking",
    "breaking news",
    "urgent",
    "news alert",
    "developing",
)


@dataclass(frozen=True)
class BreakingSource:
    url: str
    label: str = ""
    match: str = "keywords"
    keywords: tuple[str, ...] = DEFAULT_KEYWORDS
    headers: tuple[tuple[str, str], ...] = ()


def _source_from_dict(value) -> Optional[BreakingSource]:
    if not isinstance(value, dict):
        return None
    url = value.get("url")
    if not isinstance(url, str) or not url.strip():
        return None
    match_value = value.get("match")
    match = str(match_value).strip().lower() if match_value is not None else "keywords"
    if match not in {"keywords", "all"}:
        logger.warning("Ignoring breaking-news source with invalid match mode")
        return None
    keywords = value.get("keywords")
    if keywords is None:
        keywords = DEFAULT_KEYWORDS
    if not isinstance(keywords, (list, tuple)) or not all(
        isinstance(item, str) for item in keywords
    ):
        logger.warning("Ignoring breaking-news source with invalid keywords")
        return None
    headers = value.get("headers")
    if headers is None:
        headers = {}
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in headers.items()
    ):
        logger.warning("Ignoring breaking-news source with invalid headers")
        return None
    label = value.get("label")
    return BreakingSource(
        url=url.strip(),
        label=str(label).strip() if label is not None else "",
        match=match,
        keywords=tuple(item.strip().casefold() for item in keywords if item.strip()),
        headers=tuple(headers.items()),
    )


def configured_breaking_sources() -> list[BreakingSource]:
    """Load feed details from a private, untracked JSON file."""

    path = Path(os.getenv("breaking_news_config_file", "breaking-news-feeds.json"))
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError, TypeError):
        logger.warning("Could not read breaking-news source configuration")
        return []
    if not isinstance(values, list):
        logger.warning("Breaking-news source configuration must be a JSON list")
        return []
    return [source for value in values if (source := _source_from_dict(value))]


def headline_fingerprint(title: str) -> str:
    normalized = re.sub(
        r"^(breaking(?: news)?|urgent|news alert|developing)\s*[:\-–—|]*\s*",
        "",
        title.casefold(),
    )
    normalized = re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _safe_source_name(url: str) -> str:
    parsed = urlsplit(url)
    return parsed.hostname or "configured source"


class BreakingNewsWatcher:
    def __init__(
        self,
        sources: Optional[Iterable[BreakingSource]] = None,
        session=None,
        now=None,
    ):
        self.sources = list(
            configured_breaking_sources() if sources is None else sources
        )
        self.enabled = os.getenv(
            "breaking_news_enabled", "false"
        ).lower() == "true" and bool(self.sources)
        self.timeout = max(1, env_int("breaking_news_timeout", 10))
        self.max_age = max(60, env_int("breaking_news_max_age_seconds", 21600))
        self.max_feed_bytes = max(
            1024, env_int("breaking_news_max_feed_bytes", 1048576)
        )
        self.max_seen_per_source = max(
            10, env_int("breaking_news_seen_per_source", 200)
        )
        self.max_fingerprints = max(10, env_int("breaking_news_max_fingerprints", 500))
        self.state_path = Path(
            os.getenv("breaking_news_state_file", "cache/breaking-news-state.json")
        )
        self.session = session or requests.Session()
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._state = self._load_state()

    def _content(self, response) -> bytes:
        content = bytearray()
        for chunk in response.iter_content(chunk_size=16_384):
            content.extend(chunk)
            if len(content) > self.max_feed_bytes:
                raise ValueError("feed exceeds configured size limit")
        return bytes(content)

    def _prune_sources(self):
        active = {source.url for source in self.sources}
        for key in ("seen", "validators"):
            self._state[key] = {
                url: value for url, value in self._state[key].items() if url in active
            }

    def _load_state(self):
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                raise ValueError
            seen = value.get("seen", {})
            fingerprints = value.get("fingerprints", [])
            validators = value.get("validators", {})
            if (
                not isinstance(seen, dict)
                or not isinstance(fingerprints, list)
                or not isinstance(validators, dict)
            ):
                raise ValueError
            return {
                "seen": seen,
                "fingerprints": fingerprints,
                "validators": validators,
            }
        except (OSError, ValueError, TypeError):
            return {"seen": {}, "fingerprints": [], "validators": {}}

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=self.state_path.parent, prefix=".breaking-state-"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self._state, handle, indent=2, sort_keys=True)
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def _qualifies(entry: FeedEntry, source: BreakingSource) -> bool:
        if source.match == "all":
            return True
        title = entry.title.casefold()
        return any(keyword in title for keyword in source.keywords)

    def _fresh(self, entry: FeedEntry) -> bool:
        if entry.published is None:
            return True
        published = entry.published
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        return published >= self.now() - timedelta(seconds=self.max_age)

    def poll(self) -> list[FeedEntry]:
        self._prune_sources()
        new_entries = []
        changed = False
        known_fingerprints = set(self._state["fingerprints"])
        for source in self.sources:
            validator = self._state["validators"].get(source.url, {})
            headers = dict(source.headers)
            headers.setdefault(
                "User-Agent",
                os.getenv(
                    "breaking_news_user_agent",
                    "rpi-waiting-time-display/1.0 feed reader",
                ),
            )
            if validator.get("etag"):
                headers["If-None-Match"] = validator["etag"]
            if validator.get("last_modified"):
                headers["If-Modified-Since"] = validator["last_modified"]
            try:
                response = self.session.get(
                    source.url,
                    timeout=self.timeout,
                    headers=headers,
                    stream=True,
                )
                try:
                    if response.status_code == 304:
                        continue
                    response.raise_for_status()
                    entries = parse_feed(
                        self._content(response),
                        FeedSource(source.url, kind="breaking", label=source.label),
                    )
                finally:
                    response.close()
            except Exception as exc:
                logger.warning(
                    "Breaking-news poll failed for %s (%s)",
                    _safe_source_name(source.url),
                    type(exc).__name__,
                )
                continue

            previous = set(self._state["seen"].get(source.url, []))
            # An unknown feed is baseline-only. This prevents old headlines
            # from being announced after first enablement or state loss.
            if previous:
                for entry in reversed(entries):
                    fingerprint = headline_fingerprint(entry.title)
                    if (
                        entry.key not in previous
                        and fingerprint not in known_fingerprints
                        and self._qualifies(entry, source)
                        and self._fresh(entry)
                    ):
                        new_entries.append(entry)
                        known_fingerprints.add(fingerprint)
                        self._state["fingerprints"].append(fingerprint)
            self._state["seen"][source.url] = [
                entry.key for entry in entries[: self.max_seen_per_source]  # noqa: E203
            ]
            self._state["fingerprints"] = self._state["fingerprints"][
                -self.max_fingerprints :  # noqa: E203
            ]
            self._state["validators"][source.url] = {
                "etag": response.headers.get("ETag", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
            }
            changed = True
        if changed:
            try:
                self._save_state()
            except OSError as exc:
                logger.warning(
                    "Could not save breaking-news state (%s)",
                    type(exc).__name__,
                )
        return sorted(
            new_entries,
            key=lambda entry: entry.published
            or datetime.min.replace(tzinfo=timezone.utc),
        )
