"""Minimal e-paper client for validated frames from display_server.py."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import socket
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import dotenv
import requests
from PIL import Image

from display_adapter import initialize_display, return_display_lock
from display_protocol import MAX_FRAME_BYTES, parse_utc, utc_now, validate_frame_bytes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollResult:
    status: str
    sequence: int | None = None
    frame_source_created_at: str | None = None


class SystemdNotifier:
    """Small sd_notify client; no dependency or helper thread can mask a hang."""

    def __init__(self, address: str | None = None) -> None:
        self.address = address if address is not None else os.getenv("NOTIFY_SOCKET")

    def notify(self, *lines: str) -> bool:
        if not self.address:
            return False
        address = self.address
        if address.startswith("@"):
            address = "\0" + address[1:]
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.connect(address)
                sock.sendall("\n".join(lines).encode())
            return True
        except OSError as exc:
            logger.warning("Could not notify systemd: %s", exc)
            return False


@dataclass(frozen=True)
class ClientHealth:
    schema_version: int
    role: str
    boot_id: str
    pid: int
    state: str
    sequence: int | None
    etag: str | None
    last_attempt_at: str | None
    last_success_at: str | None
    last_error_at: str | None
    error: str | None
    frame_source_created_at: str | None
    server_generated_at: str | None = None
    server_received_at: str | None = None


class HealthReporter:
    """Secondary tmpfs diagnostics, updated only when meaningful state changes."""

    def __init__(self, path: str | os.PathLike[str] | None) -> None:
        self.path = Path(path) if path else None
        self._last_key = None
        try:
            self.boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        except OSError:
            self.boot_id = "unknown"

    def write(self, health: ClientHealth) -> None:
        if not self.path:
            return
        key = (health.state, health.sequence, health.etag, health.error)
        if key == self._last_key:
            return
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
            )
            with os.fdopen(descriptor, "w") as handle:
                json.dump(asdict(health), handle, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self._last_key = key
        except OSError as exc:
            if temporary:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
            logger.warning("Disabling secondary client health file: %s", exc)
            self.path = None


class FrameClient:
    def __init__(
        self,
        epd,
        *,
        url: str,
        token: str | None = None,
        max_frame_age_seconds: int = 300,
        timeout_seconds: float = 5.0,
        session=None,
        clock=utc_now,
    ) -> None:
        self.epd = epd
        self.url = url
        self.token = token
        self.max_frame_age_seconds = max(1, max_frame_age_seconds)
        self.timeout_seconds = max(0.1, timeout_seconds)
        self.session = session or requests.Session()
        self.clock = clock
        self.etag: str | None = None
        self.last_sequence = 0
        self.last_frame_created_at: str | None = None
        self.rotation = int(os.getenv("screen_rotation", "90"))
        self.full_refresh_every = max(
            1, int(os.getenv("display_client_full_refresh_every", "40"))
        )
        self.displayed_updates = 0
        self.display_lock = return_display_lock()

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "image/png"}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def poll_once(self) -> PollResult:
        response = self.session.get(
            self.url,
            headers=self._headers(),
            timeout=self.timeout_seconds,
            stream=True,
        )
        try:
            if response.status_code == 304:
                if not self.etag or self.last_sequence == 0:
                    raise ValueError("not-modified response arrived before a frame")
                created_at = response.headers.get("X-Display-Published-At")
                if not created_at:
                    raise ValueError("not-modified response omitted frame timestamp")
                self._validate_freshness(created_at)
                self.last_frame_created_at = created_at
                return PollResult(
                    "not-modified", self.last_sequence or None, created_at
                )
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type != "image/png":
                raise ValueError(
                    f"unexpected content type: {content_type or 'missing'}"
                )
            sequence = int(response.headers["X-Display-Sequence"])
            created_at = response.headers["X-Display-Published-At"]
            self._validate_freshness(created_at)
            if sequence <= self.last_sequence:
                previous = (
                    parse_utc(self.last_frame_created_at)
                    if self.last_frame_created_at
                    else None
                )
                if previous is None or parse_utc(created_at) <= previous:
                    raise ValueError(
                        "frame sequence moved backwards without a newer epoch"
                    )
            expected_length = response.headers.get("Content-Length")
            if expected_length is not None and int(expected_length) > MAX_FRAME_BYTES:
                raise ValueError("frame content length exceeds the accepted maximum")
            content = self._read_bounded(response)
            if expected_length is not None and int(expected_length) != len(content):
                raise ValueError("frame content length does not match response")
            expected_digest = response.headers.get("X-Display-SHA256")
            if not expected_digest or not hmac_digest_equal(
                hashlib.sha256(content).hexdigest(), expected_digest
            ):
                raise ValueError("frame digest does not match response")
            frame = validate_frame_bytes(content)
            self._display(frame)
            self.last_sequence = sequence
            self.etag = response.headers.get("ETag")
            self.last_frame_created_at = created_at
            return PollResult("displayed", sequence, created_at)
        finally:
            response.close()

    @staticmethod
    def _read_bounded(response) -> bytes:
        chunks = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_FRAME_BYTES:
                raise ValueError("frame body exceeds the accepted maximum")
            chunks.append(chunk)
        return b"".join(chunks)

    def _validate_freshness(self, created_at: str) -> None:
        published_at = parse_utc(created_at)
        age = (self.clock() - published_at).total_seconds()
        if age < -30:
            raise ValueError("frame timestamp is too far in the future")
        if age > self.max_frame_age_seconds:
            raise ValueError(f"frame is stale ({age:.1f}s old)")

    def _display(self, frame: Image.Image) -> None:
        image = frame.rotate(self.rotation, expand=True)
        with self.display_lock:
            use_base = self.displayed_updates % self.full_refresh_every == 0
            if use_base and self.displayed_updates > 0:
                self.epd.init()
                self.epd.Clear()
                self.epd.init_Fast()
            buffer = self.epd.getbuffer(image)
            if hasattr(self.epd, "displayPartial"):
                if use_base and hasattr(self.epd, "displayPartBaseImage"):
                    self.epd.displayPartBaseImage(buffer)
                else:
                    self.epd.displayPartial(buffer)
            else:
                self.epd.display(buffer)
            self.displayed_updates += 1


def client_display_cleanup(epd) -> None:
    """Release hardware without clearing the e-paper's persistent pixels."""
    with return_display_lock():
        epd.sleep()
        epd.epdconfig.module_exit(cleanup=True)


def hmac_digest_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


def main() -> int:
    dotenv.load_dotenv(override=True)
    import log_config  # noqa: F401 - configures application logging

    url = os.getenv("display_client_url")
    if not url:
        logger.error("display_client_url must point to /api/v1/frame.png")
        return 2
    interval = max(1.0, float(os.getenv("display_client_poll_interval", "5")))
    epd = initialize_display()
    client = FrameClient(
        epd,
        url=url,
        token=os.getenv("display_client_token") or None,
        max_frame_age_seconds=int(os.getenv("display_client_max_frame_age", "300")),
        timeout_seconds=float(os.getenv("display_client_timeout", "5")),
    )
    notifier = SystemdNotifier()
    health_reporter = HealthReporter(
        os.getenv(
            "display_client_health_path",
            "/run/rpi-waiting-time-display/client-health.json",
        )
    )
    last_attempt_at = None
    last_success_at = None
    last_error_at = None
    last_error = None
    stopping = False

    def stop(_signum=None, _frame=None):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    notifier.notify("STATUS=Display initialized; waiting for a fresh frame")
    ready_sent = False
    try:
        while not stopping:
            started = time.monotonic()
            last_attempt_at = utc_now().isoformat()
            try:
                result = client.poll_once()
                logger.debug("Frame poll result: %s", result.status)
                last_success_at = utc_now().isoformat()
                last_error = None
                notifications = [
                    "WATCHDOG=1",
                    f"STATUS=Fresh frame sequence {result.sequence} ({result.status})",
                ]
                if not ready_sent:
                    notifications.insert(0, "READY=1")
                    ready_sent = True
                notifier.notify(*notifications)
                state = "healthy"
            except (requests.RequestException, ValueError, KeyError) as exc:
                # Offline/stale policy: keep the last verified pixels. Never
                # replace them with an error page, partial response, or old PNG.
                logger.warning(
                    "Frame poll rejected; retaining last good display: %s", exc
                )
                last_error_at = utc_now().isoformat()
                last_error = str(exc)
                notifier.notify(f"STATUS=Frame poll failed: {exc}")
                state = "degraded"
            health_reporter.write(
                ClientHealth(
                    schema_version=1,
                    role="display-client",
                    boot_id=health_reporter.boot_id,
                    pid=os.getpid(),
                    state=state,
                    sequence=client.last_sequence or None,
                    etag=client.etag,
                    last_attempt_at=last_attempt_at,
                    last_success_at=last_success_at,
                    last_error_at=last_error_at,
                    error=last_error,
                    frame_source_created_at=client.last_frame_created_at,
                    server_generated_at=client.last_frame_created_at,
                    server_received_at=last_success_at,
                )
            )
            remaining = interval - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(remaining)
    finally:
        notifier.notify("STOPPING=1", "STATUS=Stopping display client")
        client_display_cleanup(epd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
