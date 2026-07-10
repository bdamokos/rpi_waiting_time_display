#!/usr/bin/env python3
"""Authenticated read-only bridge from CodexBar CLI to display-safe JSON."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import subprocess
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict


class SnapshotBuilder:
    def __init__(self, command: str, cache_seconds: int):
        self.command = command
        self.cache_seconds = cache_seconds
        self._lock = threading.Lock()
        self._cached: Dict[str, Any] | None = None
        self._cached_at = 0.0

    def _run(self, *arguments: str) -> Any:
        result = subprocess.run(
            [self.command, *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        )
        return json.loads(result.stdout)

    def build(self) -> Dict[str, Any]:
        with self._lock:
            if self._cached and time.monotonic() - self._cached_at < self.cache_seconds:
                return self._cached
            usage_rows = self._run(
                "usage", "--provider", "codex", "--source", "oauth", "--format", "json"
            )
            cost_rows = self._run("cost", "--provider", "codex", "--format", "json")
            usage = usage_rows[0]
            cost = cost_rows[0]
            month_prefix = datetime.now().strftime("%Y-%m-")
            daily = [
                {
                    "date": item["date"],
                    "cost_usd": round(float(item.get("totalCost", 0)), 6),
                    "total_tokens": int(item.get("totalTokens", 0)),
                }
                for item in cost.get("daily", [])
                if str(item.get("date", "")).startswith(month_prefix)
            ]
            primary = usage.get("usage", {}).get("primary") or {}
            secondary = usage.get("usage", {}).get("secondary") or {}
            self._cached = {
                "schema_version": 1,
                "generated_at": datetime.now().astimezone().isoformat(),
                "currency": cost.get("currencyCode", "USD"),
                "limits": {
                    "primary": {
                        "used_percent": float(primary.get("usedPercent", 0)),
                        "resets_at": primary.get("resetsAt"),
                    },
                    "secondary": {
                        "used_percent": float(secondary.get("usedPercent", 0)),
                        "resets_at": secondary.get("resetsAt"),
                    },
                },
                "month_to_date": {
                    "cost_usd": round(sum(item["cost_usd"] for item in daily), 6),
                    "total_tokens": sum(item["total_tokens"] for item in daily),
                },
                "daily": daily,
            }
            self._cached_at = time.monotonic()
            return self._cached


def token_from_environment() -> str:
    token_file = os.getenv("TOKEN_USAGE_SERVER_TOKEN_FILE", "").strip()
    if token_file:
        return Path(token_file).expanduser().read_text(encoding="utf-8").strip()
    return os.getenv("TOKEN_USAGE_SERVER_TOKEN", "").strip()


def make_handler(builder: SnapshotBuilder, token: str):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: HTTPStatus, payload: Dict[str, Any]):
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._json(HTTPStatus.OK, {"status": "ok"})
                return
            if self.path != "/snapshot":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            supplied = self.headers.get("Authorization", "")
            if token and not hmac.compare_digest(supplied, f"Bearer {token}"):
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            try:
                self._json(HTTPStatus.OK, builder.build())
            except Exception:
                self._json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    {"error": "usage source unavailable"},
                )

        def log_message(self, format, *args):
            return

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--cache-seconds", type=int, default=300)
    parser.add_argument("--codexbar-command", default="codexbar")
    args = parser.parse_args()
    token = token_from_environment()
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not token:
        parser.error("a token is required when listening beyond loopback")
    builder = SnapshotBuilder(args.codexbar_command, max(0, args.cache_seconds))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(builder, token))

    def refresh_loop():
        while True:
            try:
                builder.build()
            except Exception:
                pass
            time.sleep(max(30, args.cache_seconds))

    threading.Thread(target=refresh_loop, name="usage-refresh", daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
