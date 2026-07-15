"""Low-write runtime health reporting for the display client.

The reporter is deliberately optional.  The setup script supplies
``DISPLAY_HEALTH_PATH`` and points it at ``/run`` so normal frame updates do not
write to the SD card.  A missing or unwritable path must never break rendering.
"""

from __future__ import annotations

import functools
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

SCHEMA_VERSION = 1
_MAX_ERROR_LENGTH = 240


def _read_text(path: str, default: str = "unknown") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip() or default
    except OSError:
        return default


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


class DisplayHealthReporter:
    """Atomically report attempted and completed physical display updates."""

    def __init__(
        self,
        path: os.PathLike[str] | str,
        *,
        clock: Callable[[], float] = time.time,
        pid: Optional[int] = None,
        boot_id: Optional[str] = None,
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self._lock = threading.Lock()
        started_at = self.clock()
        self._state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "role": "display-client",
            "boot_id": (
                boot_id
                if boot_id is not None
                else _read_text("/proc/sys/kernel/random/boot_id")
            ),
            "pid": os.getpid() if pid is None else pid,
            "process_started_at": started_at,
            "sequence": 0,
            "in_progress": False,
            "last_attempt_at": None,
            "last_success_at": None,
            "last_error_at": None,
            "last_error": None,
            "last_method": None,
            "frame_source_created_at": None,
            "server_generated_at": None,
            "server_received_at": None,
        }
        self._safe_write()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def mark_attempt(
        self, method: str, *, frame_source_created_at: Optional[float] = None
    ) -> None:
        with self._lock:
            now = self.clock()
            self._state.update(
                {
                    "in_progress": True,
                    "last_attempt_at": now,
                    "last_method": method,
                    "frame_source_created_at": frame_source_created_at or now,
                }
            )
            # Do not write the pre-frame attempt.  The client loop and systemd
            # notify socket are the primary hang detector; the JSON file is a
            # rate-limited diagnostic updated only on sequence/state changes.

    def mark_success(self, method: str) -> None:
        with self._lock:
            now = self.clock()
            self._state.update(
                {
                    "sequence": int(self._state["sequence"]) + 1,
                    "in_progress": False,
                    "last_success_at": now,
                    "last_method": method,
                    "last_error": None,
                }
            )
            self._safe_write_locked()

    def mark_failure(self, method: str, error: BaseException) -> None:
        with self._lock:
            now = self.clock()
            self._state.update(
                {
                    "in_progress": False,
                    "last_error_at": now,
                    "last_error": f"{type(error).__name__}: {error}"[
                        :_MAX_ERROR_LENGTH
                    ],
                    "last_method": method,
                }
            )
            self._safe_write_locked()

    def mark_server_frame(
        self, generated_at: float, *, received_at: Optional[float] = None
    ) -> None:
        """Attach optional server freshness to subsequent client heartbeats."""

        with self._lock:
            self._state["server_generated_at"] = float(generated_at)
            self._state["server_received_at"] = (
                self.clock() if received_at is None else float(received_at)
            )
            self._safe_write_locked()

    def _safe_write(self) -> None:
        with self._lock:
            self._safe_write_locked()

    def _safe_write_locked(self) -> None:
        try:
            _atomic_json_write(self.path, self._state)
        except OSError:
            # Health reporting is diagnostic.  It must not turn a healthy frame
            # into an application failure when /run is unavailable or read-only.
            return


def instrument_display(
    display: Any, reporter: Optional[DisplayHealthReporter] = None
) -> Any:
    """Wrap successful hardware update methods with the v1 health contract."""

    if getattr(display, "_display_health_instrumented", False):
        return display

    if reporter is None:
        path = os.getenv("DISPLAY_HEALTH_PATH", "").strip()
        if not path:
            return display
        absolute_path = os.path.abspath(path)
        if os.path.commonpath((absolute_path, "/run")) != "/run":
            # Runtime health must never default to the checkout or persistent
            # storage.  Explicit reporters remain available to unit tests.
            return display
        reporter = DisplayHealthReporter(absolute_path)

    for method_name in ("display", "displayPartial", "displayPartBaseImage"):
        original = getattr(display, method_name, None)
        if not callable(original):
            continue

        @functools.wraps(original)
        def wrapped(*args: Any, __original=original, __name=method_name, **kwargs: Any):
            reporter.mark_attempt(__name)
            try:
                result = __original(*args, **kwargs)
            except BaseException as error:
                reporter.mark_failure(__name, error)
                raise
            reporter.mark_success(__name)
            return result

        setattr(display, method_name, wrapped)

    display._display_health_instrumented = True
    display._display_health_reporter = reporter
    return display
