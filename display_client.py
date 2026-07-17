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
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import dotenv
import requests
from PIL import Image, ImageDraw, ImageFont

from display_adapter import initialize_display, return_display_lock
from display_protocol import MAX_FRAME_BYTES, parse_utc, utc_now, validate_frame_bytes

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollResult:
    status: str
    sequence: int | None = None
    frame_source_created_at: str | None = None


@dataclass(frozen=True)
class DiagnosticView:
    """Sanitized local-only content for a prolonged render-server outage."""

    category: str
    clock_synchronized: bool
    lines: tuple[str, ...]


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
        self._has_displayed_anything = False
        self.last_verified_frame: Image.Image | None = None
        self.diagnostic_displayed = False
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
                status = "not-modified"
                if self.diagnostic_displayed:
                    if self.last_verified_frame is None:
                        raise ValueError(
                            "not-modified response cannot restore a verified frame"
                        )
                    self._display(self.last_verified_frame)
                    self.diagnostic_displayed = False
                    status = "restored"
                return PollResult(status, self.last_sequence or None, created_at)
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
            self.last_verified_frame = frame.copy()
            self.diagnostic_displayed = False
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

    def display_local_diagnostic(self, frame: Image.Image) -> None:
        """Display a locally generated frame without changing protocol state."""
        self._display(frame, count_server_update=False)
        self.diagnostic_displayed = True

    def _display(self, frame: Image.Image, *, count_server_update: bool = True) -> None:
        image = frame.rotate(self.rotation, expand=True)
        target_width = getattr(self.epd, "width", None)
        target_height = getattr(self.epd, "height", None)
        if (
            target_width
            and target_height
            and image.size
            != (
                target_width,
                target_height,
            )
        ):
            if image.width > target_width or image.height > target_height:
                raise ValueError(
                    "frame does not fit the hardware buffer "
                    f"({image.width}x{image.height} > "
                    f"{target_width}x{target_height})"
                )
            bands = image.getbands()
            white = (
                1
                if image.mode == "1"
                else (255 if len(bands) == 1 else tuple(255 for _ in bands))
            )
            padded = Image.new(
                image.mode,
                (target_width, target_height),
                white,
            )
            padded.paste(
                image,
                (
                    (target_width - image.width) // 2,
                    (target_height - image.height) // 2,
                ),
            )
            image = padded
        with self.display_lock:
            use_base = not self._has_displayed_anything or (
                count_server_update
                and self.displayed_updates % self.full_refresh_every == 0
            )
            if use_base and self._has_displayed_anything:
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
            self._has_displayed_anything = True
            if count_server_update:
                self.displayed_updates += 1


def categorize_poll_error(exc: BaseException) -> str:
    """Return a short stable category without leaking request details."""
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.HTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (401, 403):
            return "auth"
        if status in (408, 504):
            return "timeout"
        return "server"
    if isinstance(exc, requests.ConnectionError):
        if _exception_contains(exc, socket.gaierror):
            return "dns"
        return "connection"

    message = str(exc).lower()
    if "too far in the future" in message or "future timestamp" in message:
        return "future-timestamp"
    if "stale" in message:
        return "stale"
    if "401" in message or "403" in message:
        return "auth"
    return "protocol"


def _exception_contains(exc: BaseException, target: type[BaseException]) -> bool:
    pending = [exc]
    seen = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, target):
            return True
        for linked in (current.__cause__, current.__context__, *current.args):
            if isinstance(linked, BaseException):
                pending.append(linked)
    return False


def build_diagnostic_view(
    category: str,
    *,
    local_now: datetime,
    seconds_since_success: float | None,
    clock_synchronized: bool,
) -> DiagnosticView:
    safe_category = (
        category
        if category
        in {
            "auth",
            "connection",
            "dns",
            "future-timestamp",
            "protocol",
            "server",
            "stale",
            "timeout",
        }
        else "protocol"
    )
    if clock_synchronized:
        time_line = f"Local: {local_now.strftime('%Y-%m-%d %H:%M %Z')}"
    else:
        time_line = "Local time: not synchronized"
    if seconds_since_success is None:
        last_frame_line = "Last frame: not seen this boot"
    else:
        last_frame_line = f"Last frame: {_format_elapsed(seconds_since_success)} ago"
    return DiagnosticView(
        category=safe_category,
        clock_synchronized=clock_synchronized,
        lines=(
            "RENDER SERVER UNAVAILABLE",
            time_line,
            last_frame_line,
            f"Error: {safe_category}",
        ),
    )


def _format_elapsed(seconds: float) -> str:
    total_minutes = max(0, int(seconds)) // 60
    if total_minutes < 1:
        return "less than 1m"
    if total_minutes < 60:
        return f"{total_minutes}m"
    hours, minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h" if hours else f"{days}d"


def bounded_env_seconds(
    name: str, default: float, *, minimum: float, maximum: float
) -> float:
    return min(maximum, max(minimum, float(os.getenv(name, str(default)))))


def render_diagnostic_view(view: DiagnosticView) -> Image.Image:
    """Render with Pillow's tiny built-in font; no remote or heavy assets."""
    image = Image.new("1", (250, 120), 1)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((0, 0, 249, 22), fill=0)
    draw.text((6, 6), view.lines[0], font=font, fill=1)
    for y, line in zip((34, 55, 76), view.lines[1:]):
        draw.text((6, y), line, font=font, fill=0)
    draw.line((6, 99, 243, 99), fill=0)
    draw.text((6, 104), "Retrying verified frames", font=font, fill=0)
    return image


class OutageDiagnosticController:
    """Monotonic, low-cadence policy for prolonged local fallback."""

    def __init__(
        self,
        client: FrameClient,
        *,
        threshold_seconds: float = 300,
        cadence_seconds: float = 60,
        monotonic_clock=time.monotonic,
        local_clock=lambda: datetime.now().astimezone(),
        clock_synchronized=lambda: True,
    ) -> None:
        self.client = client
        self.threshold_seconds = max(0.0, threshold_seconds)
        self.cadence_seconds = max(0.0, cadence_seconds)
        self.monotonic_clock = monotonic_clock
        self.local_clock = local_clock
        self.clock_synchronized = clock_synchronized
        self._outage_started: float | None = None
        self._last_success: float | None = None
        self._last_rendered: float | None = None
        self._last_render_category: str | None = None
        self._last_render_sync: bool | None = None
        self._last_monotonic: float | None = None
        self._stopped = False

    @property
    def diagnostic_active(self) -> bool:
        return self.client.diagnostic_displayed

    def record_success(self) -> None:
        now = self.monotonic_clock()
        self._last_monotonic = now
        self._last_success = now
        self._outage_started = None
        self._last_rendered = None
        self._last_render_category = None
        self._last_render_sync = None

    def record_failure(self, exc: BaseException) -> bool:
        if self._stopped:
            return False
        now = self.monotonic_clock()
        if self._last_monotonic is not None and now < self._last_monotonic:
            # Treat a monotonic rollback like a new boot. Never accelerate the
            # fallback because either wall or monotonic time moved abruptly.
            self._outage_started = now
            self._last_success = None
            self._last_rendered = None
        self._last_monotonic = now
        if self._outage_started is None:
            self._outage_started = now
        if now - self._outage_started < self.threshold_seconds:
            return False

        category = categorize_poll_error(exc)
        synchronized = bool(self.clock_synchronized())
        due = (
            self._last_rendered is None
            or now - self._last_rendered >= self.cadence_seconds
            or category != self._last_render_category
            or synchronized != self._last_render_sync
        )
        if not due or self._stopped:
            return False
        elapsed = None if self._last_success is None else now - self._last_success
        view = build_diagnostic_view(
            category,
            local_now=self.local_clock(),
            seconds_since_success=elapsed,
            clock_synchronized=synchronized,
        )
        if self._stopped:
            return False
        self.client.display_local_diagnostic(render_diagnostic_view(view))
        self._last_rendered = now
        self._last_render_category = category
        self._last_render_sync = synchronized
        return True

    def shutdown(self) -> None:
        self._stopped = True


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
    diagnostic_threshold = bounded_env_seconds(
        "display_client_diagnostic_after",
        300,
        minimum=30,
        maximum=86400,
    )
    diagnostic_cadence = bounded_env_seconds(
        "display_client_diagnostic_cadence",
        60,
        minimum=30,
        maximum=3600,
    )
    clock_sync_path = os.getenv(
        "display_client_clock_sync_path",
        "/run/systemd/timesync/synchronized",
    )
    outage_diagnostic = OutageDiagnosticController(
        client,
        threshold_seconds=diagnostic_threshold,
        cadence_seconds=diagnostic_cadence,
        clock_synchronized=lambda: not clock_sync_path
        or Path(clock_sync_path).exists(),
    )
    last_attempt_at = None
    last_success_at = None
    last_error_at = None
    last_error = None
    shutdown_event = threading.Event()

    def stop(_signum=None, _frame=None):
        outage_diagnostic.shutdown()
        shutdown_event.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    notifier.notify(
        "READY=1",
        "STATUS=Display initialized; waiting for a fresh frame",
    )
    try:
        while not shutdown_event.is_set():
            started = time.monotonic()
            last_attempt_at = utc_now().isoformat()
            try:
                result = client.poll_once()
                logger.debug("Frame poll result: %s", result.status)
                outage_diagnostic.record_success()
                last_success_at = utc_now().isoformat()
                last_error = None
                notifier.notify(
                    "WATCHDOG=1",
                    f"STATUS=Fresh frame sequence {result.sequence} ({result.status})",
                )
                state = "healthy"
            except (requests.RequestException, ValueError, KeyError) as exc:
                if shutdown_event.is_set():
                    break
                category = categorize_poll_error(exc)
                diagnostic_updated = outage_diagnostic.record_failure(exc)
                logger.warning(
                    "Frame poll rejected; retaining safe display (category=%s)",
                    category,
                )
                last_error_at = utc_now().isoformat()
                last_error = category
                fallback = (
                    "local diagnostic active"
                    if outage_diagnostic.diagnostic_active
                    else "retaining last verified pixels"
                )
                notifier.notify(
                    "WATCHDOG=1",
                    f"STATUS=Frame poll failed ({category}); {fallback}",
                )
                if diagnostic_updated:
                    logger.info("Updated local outage diagnostic (%s)", category)
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
                shutdown_event.wait(remaining)
    finally:
        notifier.notify("STOPPING=1", "STATUS=Stopping display client")
        client_display_cleanup(epd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
