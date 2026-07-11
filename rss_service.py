"""Small, dependency-free RSS/Atom watcher used by the display plugin."""

from __future__ import annotations

import hashlib
import html
import json
import logging
import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def clean_text(value: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html.unescape(value or ""))
        value = " ".join(parser.parts)
    except Exception:
        value = value or ""
    return " ".join(value.split())


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child(element, *names):
    names = {name.lower() for name in names}
    return next((child for child in element if _local_name(child.tag) in names), None)


def _text(element, *names) -> str:
    child = _child(element, *names)
    return "" if child is None else "".join(child.itertext()).strip()


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True)
class FeedSource:
    url: str
    kind: str = "rss"
    label: str = ""
    handle: str = ""


@dataclass(frozen=True)
class FeedEntry:
    key: str
    source_url: str
    kind: str
    publication: str
    title: str
    link: str = ""
    author: str = ""
    handle: str = ""
    avatar_url: str = ""
    published: Optional[datetime] = None


def configured_sources() -> list[FeedSource]:
    sources = []
    nitter_base = os.getenv("rss_nitter_base_url", "").strip().rstrip("/")
    for handle in os.getenv("rss_nitter_users", "").split(","):
        handle = handle.strip().lstrip("@")
        if handle and nitter_base:
            sources.append(
                FeedSource(
                    f"{nitter_base}/{handle}/rss",
                    kind="nitter",
                    handle=f"@{handle}",
                )
            )
    for url in os.getenv("rss_feed_urls", "").split(","):
        if url.strip():
            sources.append(FeedSource(url.strip()))
    return sources


def parse_feed(content: bytes, source: FeedSource) -> list[FeedEntry]:
    root = ET.fromstring(content)
    channel_element = _child(root, "channel")
    channel = channel_element if channel_element is not None else root
    publication = source.label or clean_text(_text(channel, "title")) or "RSS"
    image = _child(channel, "image")
    avatar_url = _text(image, "url") if image is not None else ""
    entries = [
        node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}
    ]
    parsed = []
    for node in entries:
        title = clean_text(_text(node, "title"))
        summary = clean_text(_text(node, "description", "summary", "content"))
        if not title:
            title = summary
        author = clean_text(_text(node, "creator", "author"))
        author_node = _child(node, "author")
        if author_node is not None and not author:
            author = clean_text(_text(author_node, "name"))
        link_node = _child(node, "link")
        link = ""
        if link_node is not None:
            link = link_node.attrib.get("href", "") or (link_node.text or "").strip()
        link = urljoin(source.url, link)
        identity = (
            _text(node, "guid", "id")
            or link
            or f"{title}|{_text(node, 'pubdate', 'published', 'updated')}"
        )
        key = hashlib.sha256(f"{source.url}|{identity}".encode()).hexdigest()
        published = _parse_date(_text(node, "pubdate", "published", "updated", "date"))
        parsed.append(
            FeedEntry(
                key=key,
                source_url=source.url,
                kind=source.kind,
                publication=publication,
                title=title or "New post",
                link=link,
                author=author,
                handle=source.handle,
                avatar_url=urljoin(source.url, avatar_url),
                published=published,
            )
        )
    return parsed


class RSSWatcher:
    def __init__(self, sources: Optional[Iterable[FeedSource]] = None, session=None):
        self.sources = list(configured_sources() if sources is None else sources)
        self.enabled = os.getenv(
            "rss_watch_enabled", "false"
        ).lower() == "true" and bool(self.sources)
        self.timeout = max(1, int(os.getenv("rss_watch_timeout", "10")))
        self.show_existing = (
            os.getenv("rss_watch_show_existing", "false").lower() == "true"
        )
        self.state_path = Path(
            os.getenv("rss_watch_state_file", "cache/rss-watch-state.json")
        )
        self.session = session or requests.Session()
        self._seen = self._load_state()

    def _load_state(self):
        try:
            data = json.loads(self.state_path.read_text())
            return {url: list(keys) for url, keys in data.get("seen", {}).items()}
        except (OSError, ValueError, TypeError):
            return {}

    def _save_state(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"seen": self._seen}, indent=2, sort_keys=True)
        fd, temporary = tempfile.mkstemp(
            dir=self.state_path.parent, prefix=".rss-state-"
        )
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(payload)
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def poll(self) -> list[FeedEntry]:
        new_entries = []
        changed = False
        for source in self.sources:
            try:
                response = self.session.get(source.url, timeout=self.timeout)
                response.raise_for_status()
                entries = parse_feed(response.content, source)
            except Exception as exc:
                logger.warning(
                    "RSS poll failed for %s (%s)", source.url, type(exc).__name__
                )
                continue
            previous = set(self._seen.get(source.url, []))
            if previous or self.show_existing:
                new_entries.extend(
                    entry for entry in reversed(entries) if entry.key not in previous
                )
            if entries:
                self._seen[source.url] = [entry.key for entry in entries[:100]]
                changed = True
        if changed:
            try:
                self._save_state()
            except OSError as exc:
                logger.warning("Could not save RSS state (%s)", type(exc).__name__)
        return sorted(
            new_entries,
            key=lambda entry: entry.published
            or datetime.min.replace(tzinfo=timezone.utc),
        )
