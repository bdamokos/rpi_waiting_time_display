"""HTTP API and runtime entrypoint for hardware-free display rendering."""

from __future__ import annotations

import hmac
import io
import logging
import os
import signal
import sys
import threading
from datetime import timezone

import dotenv
from flask import Flask, Response, jsonify, request, send_file
from werkzeug.serving import make_server

from display_protocol import FramePublisher, parse_utc, utc_now
from publication_display import PublicationDisplay

logger = logging.getLogger(__name__)


def _as_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _authorized(expected_token: str | None) -> bool:
    if not expected_token:
        return True
    supplied = request.headers.get("Authorization", "")
    prefix = "Bearer "
    return supplied.startswith(prefix) and hmac.compare_digest(
        supplied[len(prefix) :], expected_token
    )


def create_app(
    publisher: FramePublisher,
    *,
    token: str | None = None,
    ready_max_age_seconds: int = 300,
) -> Flask:
    app = Flask(__name__)

    @app.after_request
    def secure_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/healthz")
    def health():
        snapshot = publisher.snapshot()
        return jsonify(
            status="ok",
            service="display-render-server",
            sequence=snapshot.metadata.sequence if snapshot else None,
            generated_at=snapshot.metadata.published_at if snapshot else None,
        )

    @app.get("/readyz")
    def readiness():
        snapshot = publisher.snapshot()
        if snapshot is None:
            return jsonify(status="not-ready", reason="no-frame"), 503
        age = (utc_now() - parse_utc(snapshot.metadata.published_at)).total_seconds()
        status = 200 if age <= ready_max_age_seconds else 503
        return (
            jsonify(
                status="ready" if status == 200 else "not-ready",
                reason=None if status == 200 else "stale-frame",
                sequence=snapshot.metadata.sequence,
                published_at=snapshot.metadata.published_at,
                age_seconds=max(0, round(age, 3)),
            ),
            status,
        )

    @app.get("/api/v1/status")
    def status():
        if not _authorized(token):
            return Response(status=401, headers={"WWW-Authenticate": "Bearer"})
        snapshot = publisher.snapshot()
        if snapshot is None:
            return jsonify(status="not-ready", frame=None), 503
        return jsonify(status="ready", frame=snapshot.metadata.__dict__)

    @app.get("/api/v1/frame.png")
    def frame():
        if not _authorized(token):
            return Response(status=401, headers={"WWW-Authenticate": "Bearer"})
        snapshot = publisher.snapshot()
        if snapshot is None:
            return jsonify(error="frame not available"), 503
        common_headers = {
            "Cache-Control": "private, no-cache, must-revalidate",
            "ETag": snapshot.etag,
            "X-Display-Sequence": str(snapshot.metadata.sequence),
            "X-Display-Published-At": snapshot.metadata.published_at,
            "X-Display-SHA256": snapshot.metadata.sha256,
        }
        if request.headers.get("If-None-Match") == snapshot.etag:
            return Response(status=304, headers=common_headers)
        return (
            send_file(
                io.BytesIO(snapshot.content),
                mimetype="image/png",
                download_name="display.png",
                etag=False,
                last_modified=parse_utc(snapshot.metadata.published_at).astimezone(
                    timezone.utc
                ),
                max_age=0,
                conditional=False,
            ),
            200,
            common_headers,
        )

    return app


def _validate_bind_security(host: str, token: str | None) -> None:
    loopback = host in {"127.0.0.1", "::1", "localhost"}
    if loopback or token or _as_bool("display_server_allow_unauthenticated"):
        return
    raise RuntimeError(
        "display_server_token is required for a non-loopback bind; set "
        "display_server_allow_unauthenticated=true only on a trusted isolated network"
    )


def main() -> int:
    dotenv.load_dotenv(override=True)
    import log_config  # noqa: F401 - configures application logging
    from basic import DisplayManager

    host = os.getenv("display_server_host", "127.0.0.1")
    port = int(os.getenv("display_server_port", "8787"))
    token = os.getenv("display_server_token") or None
    _validate_bind_security(host, token)
    publisher = FramePublisher(
        os.getenv("display_server_frame_dir", "/run/rpi-waiting-time-display/frames")
    )
    app = create_app(
        publisher,
        token=token,
        ready_max_age_seconds=max(
            1, int(os.getenv("display_server_ready_max_age", "300"))
        ),
    )
    display = PublicationDisplay(publisher)
    manager = DisplayManager(display)
    server = make_server(host, port, app, threaded=True)

    def stop(_signum=None, _frame=None):
        # BaseServer.shutdown must run outside the serve_forever thread.
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        manager.start()
        logger.info("Display render server listening on %s:%s", host, port)
        server.serve_forever()
    finally:
        manager.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
