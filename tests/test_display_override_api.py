from display_override_api import (
    DisplayOverrideServer,
    _is_private_client,
    create_override_app,
)
from screen_arbiter import ScreenArbiter


def _blocking_calendar_override(manager, monkeypatch):
    import threading
    from types import SimpleNamespace

    from calendar_plugin import CalendarPlugin
    from plugins import PluginContext

    fetch_started = threading.Event()
    fetch_continue = threading.Event()
    rendered = []

    def get_events(now):
        fetch_started.set()
        assert fetch_continue.wait(timeout=2)
        return []

    client = SimpleNamespace(
        enabled=True,
        timezone=None,
        get_events=get_events,
    )
    plugin = CalendarPlugin(
        PluginContext(
            manager.epd,
            manager.screen_arbiter,
            manager._display_lock,
        ),
        client=client,
    )
    monkeypatch.setattr(
        "calendar_plugin.draw_calendar_agenda",
        lambda *args, **kwargs: rendered.append(True),
    )
    manager.calendar_plugin = plugin
    manager._display_override_handlers = {
        "calendar": plugin.render_forced_agenda,
        "token": lambda owner, is_current: is_current(),
    }
    manager._display_override_aliases = manager.OVERRIDE_MODULE_ALIASES
    manager._force_display_update = lambda: None
    return fetch_started, fetch_continue, rendered


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
    manager._override_generation = 0
    manager._override_lock = threading.RLock()
    manager._override_render_lock = threading.Lock()
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


def test_unknown_override_preserves_legacy_alias_response_shape():
    from basic import DisplayManager

    manager = DisplayManager.__new__(DisplayManager)

    assert manager.request_display_override("nope") == {
        "accepted": False,
        "error": "unknown module",
        "modules": [
            "bus",
            "calendar",
            "codex",
            "flight-records",
            "flight-stats",
            "flight_records",
            "flight_stats",
            "flight_stats_day",
            "flight_stats_month",
            "flight_stats_week",
            "flights",
            "iss",
            "token",
            "transit",
            "weather",
        ],
    }


def test_declarative_plugin_override_extends_legacy_modules():
    from types import SimpleNamespace

    from basic import DisplayManager
    from plugins import DisplayOverride

    manager = DisplayManager.__new__(DisplayManager)
    calendar = DisplayOverride("calendar", lambda owner, is_current: is_current())
    extra = DisplayOverride("extra", lambda owner, is_current: is_current())
    manager.plugin_registry = SimpleNamespace(display_overrides=(calendar, extra))

    manager._configure_display_overrides()

    assert manager._display_override_aliases == {
        **manager.OVERRIDE_MODULE_ALIASES,
        "extra": "extra",
    }
    assert manager._display_override_handlers["extra"] is extra.render


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
        lambda module=None, generation=None: rendered_modules.append(module) or False
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
        lambda module=None, generation=None: rendered_modules.append(module) or True
    )

    result = manager.request_display_override("codex")

    assert result["module"] == "token"
    assert rendered_modules == ["token"]
    assert manager._last_screen_owner == manager.OVERRIDE_SCREEN_OWNER
    assert manager.display_override_status()["modules"] == [
        "calendar",
        "flight_records",
        "flight_stats_day",
        "flight_stats_month",
        "flight_stats_week",
        "flights",
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

    def render(module=None, generation=None):
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


def test_slow_calendar_override_is_superseded_without_rendering(
    monkeypatch, tmp_path
):
    import threading

    manager = _display_manager_for_override(monkeypatch, tmp_path)
    fetch_started, fetch_continue, rendered = _blocking_calendar_override(
        manager, monkeypatch
    )
    result = {}
    request = threading.Thread(
        target=lambda: result.update(manager.request_display_override("calendar"))
    )
    request.start()
    assert fetch_started.wait(timeout=2)

    newer = manager.request_display_override("codex")
    fetch_continue.set()
    request.join(timeout=2)

    assert newer["rendered"] is True
    assert result["rendered"] is False
    assert rendered == []
    assert manager._override_module == "token"
    assert manager.screen_arbiter.active_owner() == manager.OVERRIDE_SCREEN_OWNER


def test_clear_supersedes_slow_calendar_override_without_rendering(
    monkeypatch, tmp_path
):
    import threading

    manager = _display_manager_for_override(monkeypatch, tmp_path)
    fetch_started, fetch_continue, rendered = _blocking_calendar_override(
        manager, monkeypatch
    )
    result = {}
    request = threading.Thread(
        target=lambda: result.update(manager.request_display_override("calendar"))
    )
    request.start()
    assert fetch_started.wait(timeout=2)

    cleared = manager.clear_display_override()
    fetch_continue.set()
    request.join(timeout=2)

    assert cleared == {"cleared": True, "active_owner": None}
    assert result["rendered"] is False
    assert rendered == []
    assert manager._override_module is None
    assert manager.screen_arbiter.active_owner() is None
