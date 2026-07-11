from display_override_api import (
    DisplayOverrideServer,
    _is_private_client,
    create_override_app,
)
from screen_arbiter import ScreenArbiter


def _display_manager_for_override(monkeypatch, tmp_path):
    import threading
    from types import SimpleNamespace

    import iss
    from basic import DisplayManager
    from display_adapter import MockDisplay
    from screen_arbiter import ScreenArbiter

    monkeypatch.chdir(tmp_path)
    manager = DisplayManager.__new__(DisplayManager)
    manager.epd = MockDisplay()
    manager.screen_arbiter = ScreenArbiter()
    manager.override_priority = 30
    manager.override_duration_seconds = 300
    manager._override_module = None
    manager._override_lock = threading.RLock()
    manager._display_lock = threading.Lock()
    manager.iss_tracker = SimpleNamespace(
        next_known_pass=lambda now: {"risetime": now + 600, "duration": 300}
    )
    manager.current_display_mode = None
    manager.current_token_view = None
    manager.in_weather_mode = False
    manager.last_display_update = None
    monkeypatch.setattr(iss, "display_next_iss_pass", lambda *args, **kwargs: None)
    return manager


def test_private_client_detection():
    assert _is_private_client("127.0.0.1")
    assert _is_private_client("192.168.1.20")
    assert _is_private_client("fd00::1")
    assert not _is_private_client("8.8.8.8")
    assert not _is_private_client("invalid")


def test_override_server_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("display_override_api_host", raising=False)

    server = DisplayOverrideServer(lambda module: {}, lambda: {}, lambda: {})

    assert server.host == "127.0.0.1"


def test_override_api_accepts_json_and_path():
    calls = []
    app = create_override_app(
        lambda module: calls.append(module) or {"accepted": True, "module": module},
        lambda: {"cleared": True},
        lambda: {"module": None},
    )
    client = app.test_client()

    assert client.post("/api/display", json={"module": "weather"}).status_code == 202
    assert client.post("/api/display/codex").status_code == 202
    assert calls == ["weather", "codex"]
    assert client.get("/api/display").get_json() == {"module": None}
    assert client.delete("/api/display").get_json() == {"cleared": True}


def test_override_api_validates_access_auth_and_payload():
    app = create_override_app(
        lambda module: {"accepted": False, "error": "unknown module"},
        lambda: {},
        lambda: {},
        token="secret",
    )
    client = app.test_client()

    assert (
        client.get("/api/display", environ_base={"REMOTE_ADDR": "8.8.8.8"}).status_code
        == 403
    )
    assert client.get("/api/display").status_code == 401
    headers = {"Authorization": "Bearer secret"}
    assert client.post("/api/display", headers=headers, json={}).status_code == 400
    assert client.post("/api/display", headers=headers, json=[]).status_code == 400
    assert (
        client.post("/api/display", headers=headers, json="weather").status_code
        == 400
    )
    assert client.post("/api/display/nope", headers=headers).status_code == 404


def test_iss_override_renders_cached_prediction(monkeypatch, tmp_path):
    manager = _display_manager_for_override(monkeypatch, tmp_path)

    result = manager.request_display_override("iss")

    assert result["accepted"] is True
    assert result["rendered"] is True
    assert manager.current_display_mode == "iss-prediction"


def test_live_iss_owner_keeps_priority_over_prediction_override(monkeypatch, tmp_path):
    manager = _display_manager_for_override(monkeypatch, tmp_path)
    assert manager.screen_arbiter.claim(manager.ISS_SCREEN_OWNER, 60, 60)

    result = manager.request_display_override("iss")

    assert result["accepted"] is True
    assert result["rendered"] is False
    assert result["active_owner"] == manager.ISS_SCREEN_OWNER


def test_failed_override_releases_active_claim(monkeypatch):
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.screen_arbiter = ScreenArbiter()
    manager.override_priority = 30
    manager.override_duration_seconds = 300
    manager._override_module = None
    manager._override_generation = 0
    import threading

    manager._override_lock = threading.RLock()
    rendered_modules = []
    manager._render_display_override = (
        lambda module=None: rendered_modules.append(module) or False
    )
    restored = []
    manager._force_display_update = lambda: restored.append(True)

    result = manager.request_display_override("weather")

    assert result["accepted"]
    assert not result["rendered"]
    assert manager.screen_arbiter.active_owner() is None
    assert manager._override_module is None
    assert rendered_modules == ["weather"]
    assert restored == [True]


def test_successful_override_records_owner_and_reports_canonical_modules():
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.screen_arbiter = ScreenArbiter()
    manager.override_priority = 30
    manager.override_duration_seconds = 300
    manager._override_module = None
    manager._override_generation = 0
    manager._last_screen_owner = None
    import threading

    manager._override_lock = threading.RLock()
    rendered_modules = []
    manager._render_display_override = (
        lambda module=None: rendered_modules.append(module) or True
    )

    result = manager.request_display_override("codex")

    assert result["module"] == "token"
    assert rendered_modules == ["token"]
    assert manager._last_screen_owner == manager.OVERRIDE_SCREEN_OWNER
    assert manager.display_override_status()["modules"] == [
        "calendar",
        "iss",
        "token",
        "transit",
        "weather",
    ]


def test_failed_request_does_not_release_a_newer_override():
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)
    manager.screen_arbiter = ScreenArbiter()
    manager.override_priority = 30
    manager.override_duration_seconds = 300
    manager._override_module = None
    manager._override_generation = 0
    manager._last_screen_owner = None
    import threading

    manager._override_lock = threading.RLock()

    def render(module=None):
        if module == "weather":
            newer = manager.request_display_override("token")
            assert newer["rendered"]
            return False
        return True

    manager._render_display_override = render
    manager._force_display_update = lambda: None

    older = manager.request_display_override("weather")

    assert not older["rendered"]
    assert manager._override_module == "token"
    assert manager.screen_arbiter.active_owner() == manager.OVERRIDE_SCREEN_OWNER
