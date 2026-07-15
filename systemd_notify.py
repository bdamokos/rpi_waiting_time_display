"""Tiny sd_notify client used directly by the display process.

No helper process emits watchdog keepalives.  The main display process calls
this module only after it has verified that its own control loop and physical
display-success policy are current.
"""

from __future__ import annotations

import os
import socket
import time
from typing import Callable, Mapping, Optional


class SystemdNotifier:
    def __init__(
        self,
        environ: Optional[Mapping[str, str]] = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        pid: Optional[int] = None,
    ) -> None:
        values = os.environ if environ is None else environ
        self._socket_path = values.get("NOTIFY_SOCKET", "")
        self._pid = os.getpid() if pid is None else pid
        self._monotonic = monotonic
        self._ready = False
        self._last_watchdog_at = 0.0

        try:
            watchdog_usec = int(values.get("WATCHDOG_USEC", "0"))
        except ValueError:
            watchdog_usec = 0
        watchdog_pid = values.get("WATCHDOG_PID", "")
        pid_matches = not watchdog_pid or watchdog_pid == str(self._pid)
        self.watchdog_interval = watchdog_usec / 1_000_000 if pid_matches else 0.0
        self.enabled = bool(self._socket_path and self.watchdog_interval > 0)

    def notify(self, *fields: str) -> bool:
        if not self._socket_path or not fields:
            return False
        address = self._socket_path
        if address.startswith("@"):
            address = "\0" + address[1:]
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as client:
                client.connect(address)
                client.sendall("\n".join(fields).encode("utf-8"))
            return True
        except OSError:
            return False

    def ready(self, status: str) -> bool:
        if self._ready:
            return True
        sent = self.notify("READY=1", f"STATUS={status}")
        self._ready = sent
        return sent

    def watchdog(self, status: str) -> bool:
        """Send a keepalive at most twice per configured watchdog interval."""

        if not self.enabled or not self._ready:
            return False
        now = self._monotonic()
        if now - self._last_watchdog_at < self.watchdog_interval / 2:
            return False
        sent = self.notify("WATCHDOG=1", f"STATUS={status}")
        if sent:
            self._last_watchdog_at = now
        return sent
