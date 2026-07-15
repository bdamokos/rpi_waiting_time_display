"""Shared frame publication and validation for split server/client operation."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image

FRAME_WIDTH = 250
FRAME_HEIGHT = 120
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_FRAME_BYTES = 2 * 1024 * 1024


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("frame timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_frame_bytes(content: bytes) -> Image.Image:
    """Validate a bounded, exact-size PNG and return a detached image."""
    if not content.startswith(PNG_SIGNATURE):
        raise ValueError("response is not a PNG")
    if not content or len(content) > MAX_FRAME_BYTES:
        raise ValueError("PNG size is outside the accepted range")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            if image.format != "PNG":
                raise ValueError("response is not a PNG")
            if image.size != (FRAME_WIDTH, FRAME_HEIGHT):
                actual = f"{image.size[0]}x{image.size[1]}"
                raise ValueError(
                    f"frame must be {FRAME_WIDTH}x{FRAME_HEIGHT}, got {actual}"
                )
            return image.copy()
    except (OSError, SyntaxError) as exc:
        raise ValueError("PNG content is invalid") from exc


@dataclass(frozen=True)
class FrameMetadata:
    sequence: int
    published_at: str
    sha256: str
    content_length: int
    width: int = FRAME_WIDTH
    height: int = FRAME_HEIGHT
    format: str = "PNG"


@dataclass(frozen=True)
class FrameSnapshot:
    metadata: FrameMetadata
    content: bytes

    @property
    def etag(self) -> str:
        return f'"{self.metadata.sequence}-{self.metadata.sha256}"'


class FramePublisher:
    """Publishes latest.png and metadata with atomic replacements."""

    def __init__(
        self,
        directory: str | os.PathLike[str],
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.directory = Path(directory)
        self.frame_path = self.directory / "latest.png"
        self.metadata_path = self.directory / "latest.json"
        self._clock = clock
        self._lock = threading.RLock()
        self._snapshot: FrameSnapshot | None = None
        self.directory.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _load_existing(self) -> None:
        try:
            metadata = FrameMetadata(**json.loads(self.metadata_path.read_text()))
            content = self.frame_path.read_bytes()
            validate_frame_bytes(content)
            if len(content) != metadata.content_length:
                raise ValueError("stored frame length does not match metadata")
            if hashlib.sha256(content).hexdigest() != metadata.sha256:
                raise ValueError("stored frame digest does not match metadata")
            parse_utc(metadata.published_at)
            self._snapshot = FrameSnapshot(metadata, content)
        except FileNotFoundError:
            return
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            # A torn or manually edited state is not readiness. The next render
            # repairs it without ever serving an unverified frame.
            self._snapshot = None

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise

    def publish(self, image: Image.Image) -> FrameSnapshot:
        if image.size != (FRAME_WIDTH, FRAME_HEIGHT):
            raise ValueError(
                f"published frame must be {FRAME_WIDTH}x{FRAME_HEIGHT}, got {image.size}"
            )
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=False)
        content = output.getvalue()
        validate_frame_bytes(content)

        with self._lock:
            sequence = self._snapshot.metadata.sequence + 1 if self._snapshot else 1
            metadata = FrameMetadata(
                sequence=sequence,
                published_at=self._clock().astimezone(timezone.utc).isoformat(),
                sha256=hashlib.sha256(content).hexdigest(),
                content_length=len(content),
            )
            # The image is replaced first and the commit marker (metadata)
            # second. In-process readers only see the snapshot after both land.
            self._atomic_write(self.frame_path, content)
            self._atomic_write(
                self.metadata_path,
                (json.dumps(asdict(metadata), sort_keys=True) + "\n").encode(),
            )
            self._snapshot = FrameSnapshot(metadata, content)
            return self._snapshot

    def snapshot(self) -> FrameSnapshot | None:
        with self._lock:
            return self._snapshot
