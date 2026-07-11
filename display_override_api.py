"""Private-network HTTP API for temporary display overrides."""

from __future__ import annotations

import hmac
import ipaddress
import logging
import os
import threading
from typing import Callable, Optional

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

logger = logging.getLogger(__name__)


def _is_private_client(address: Optional[str]) -> bool:
    try:
        client = ipaddress.ip_address(address or "")
    except ValueError:
        return False
    return client.is_private or client.is_loopback


def create_override_app(
    request_override: Callable[[str], dict],
    clear_override: Callable[[], dict],
    get_status: Callable[[], dict],
    *,
    token: str = "",
) -> Flask:
    """Create the API app around DisplayManager callbacks."""

    app = Flask(__name__)

    @app.before_request
    def restrict_access():
        if not _is_private_client(request.remote_addr):
            return jsonify(error="private network access required"), 403
        if token:
            supplied = request.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied, f"Bearer {token}"):
                return jsonify(error="invalid bearer token"), 401
        return None

    @app.get("/api/display")
    def status():
        return jsonify(get_status())

    @app.post("/api/display")
    def override_from_json():
        body = request.get_json(silent=True) or {}
        module = body.get("module")
        if not isinstance(module, str) or not module.strip():
            return jsonify(error="JSON field 'module' is required"), 400
        return _override_response(module)

    @app.post("/api/display/<module>")
    def override_from_path(module):
        return _override_response(module)

    @app.delete("/api/display")
    def clear():
        return jsonify(clear_override())

    def _override_response(module):
        result = request_override(module)
        status_code = 202 if result.get("accepted") else 409
        if result.get("error") == "unknown module":
            status_code = 404
        return jsonify(result), status_code

    return app


class DisplayOverrideServer:
    """Run the override API in a stoppable background thread.

    The listener defaults to loopback. Operators must explicitly configure a
    LAN address when remote private-network clients need access.
    """

    def __init__(self, request_override, clear_override, get_status):
        self.enabled = (
            os.getenv("display_override_api_enabled", "false").lower() == "true"
        )
        self.host = os.getenv("display_override_api_host", "127.0.0.1")
        self.port = int(os.getenv("display_override_api_port", "5003"))
        token = os.getenv("display_override_api_token", "")
        self.app = create_override_app(
            request_override,
            clear_override,
            get_status,
            token=token,
        )
        self._server = None
        self._thread = None

    def start(self):
        if not self.enabled or self._thread:
            return
        self._server = make_server(self.host, self.port, self.app, threaded=True)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="DisplayOverrideAPI",
            daemon=True,
        )
        self._thread.start()
        logger.info("Display override API listening on %s:%s", self.host, self.port)

    def stop(self):
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None
