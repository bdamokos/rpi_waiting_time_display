from datetime import datetime, timedelta, timezone

from PIL import Image

import display_server
from display_protocol import FramePublisher
from display_server import _validate_bind_security, create_app

NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def test_health_readiness_auth_and_conditional_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(display_server, "utc_now", lambda: NOW)
    publisher = FramePublisher(tmp_path, clock=lambda: NOW)
    app = create_app(publisher, token="secret", ready_max_age_seconds=300)
    client = app.test_client()

    health = client.get("/healthz").get_json()
    assert health["sequence"] is None
    assert health["version"] == "0.3.0"
    assert client.get("/readyz").status_code == 503
    assert client.get("/api/v1/frame.png").status_code == 401

    published = publisher.publish(Image.new("1", (250, 120), 1))
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.get_json()["sequence"] == 1

    response = client.get(
        "/api/v1/frame.png", headers={"Authorization": "Bearer secret"}
    )
    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert response.headers["X-Display-Sequence"] == "1"
    assert response.headers["X-Display-SHA256"] == published.metadata.sha256
    assert response.headers["Cache-Control"] == "private, no-cache, must-revalidate"

    cached = client.get(
        "/api/v1/frame.png",
        headers={
            "Authorization": "Bearer secret",
            "If-None-Match": response.headers["ETag"],
        },
    )
    assert cached.status_code == 304
    assert cached.headers["X-Display-Sequence"] == "1"


def test_readiness_rejects_stale_frame(tmp_path, monkeypatch):
    publisher = FramePublisher(tmp_path, clock=lambda: NOW)
    publisher.publish(Image.new("1", (250, 120), 1))
    monkeypatch.setattr(display_server, "utc_now", lambda: NOW + timedelta(seconds=301))
    response = (
        create_app(publisher, ready_max_age_seconds=300).test_client().get("/readyz")
    )
    assert response.status_code == 503
    assert response.get_json()["reason"] == "stale-frame"


def test_non_loopback_bind_requires_token(monkeypatch):
    monkeypatch.delenv("display_server_allow_unauthenticated", raising=False)
    _validate_bind_security("127.0.0.1", None)
    _validate_bind_security("0.0.0.0", "secret")
    try:
        _validate_bind_security("0.0.0.0", None)
    except RuntimeError as exc:
        assert "token is required" in str(exc)
    else:
        raise AssertionError("insecure non-loopback bind was accepted")
