import threading
from dataclasses import FrozenInstanceError

import pytest

from plugins import (
    ConfigError,
    DisplayOverride,
    DisplayPlugin,
    OverrideCapability,
    PeriodicRotatingScreen,
    PluginContext,
    PluginRegistry,
    RotatingView,
    env_bool,
    env_float,
    env_int,
    env_json_list,
    env_json_object,
)
from screen_arbiter import ScreenArbiter


class FakePlugin:
    override_capabilities = ()

    def __init__(
        self,
        name,
        events,
        fail_start=False,
        fail_stop=False,
        display_overrides=(),
    ):
        self.name = name
        self.display_overrides = display_overrides
        self.events = events
        self.fail_start = fail_start
        self.fail_stop = fail_stop

    def start(self):
        self.events.append(f"start:{self.name}")
        if self.fail_start:
            raise RuntimeError("start failed")

    def stop(self):
        self.events.append(f"stop:{self.name}")
        if self.fail_stop:
            raise RuntimeError("stop failed")


def test_plugin_context_and_override_capability_are_immutable():
    context = PluginContext(object(), ScreenArbiter(), threading.Lock())
    capability = OverrideCapability(" alerts ", "42", exclusive=True)

    with pytest.raises(FrozenInstanceError):
        context.epd = object()
    with pytest.raises(FrozenInstanceError):
        capability.priority = 1
    assert capability.owner == "alerts"
    assert capability.priority == 42


def test_registry_starts_in_order_stops_in_reverse_and_isolates_failures():
    events = []
    registry = PluginRegistry(
        [
            FakePlugin("first", events),
            FakePlugin("broken-start", events, fail_start=True),
            FakePlugin("broken-stop", events, fail_stop=True),
            FakePlugin("last", events),
        ]
    )

    registry.start_all()
    registry.stop_all()

    assert events == [
        "start:first",
        "start:broken-start",
        "stop:broken-start",
        "start:broken-stop",
        "start:last",
        "stop:last",
        "stop:broken-stop",
        "stop:first",
    ]


def test_registry_rejects_duplicate_names_and_exposes_stable_order():
    events = []
    first = FakePlugin("same", events)
    registry = PluginRegistry([first])

    with pytest.raises(ValueError, match="duplicate plugin name"):
        registry.register(FakePlugin("same", events))
    assert registry.plugins == (first,)
    assert registry.get("same") is first


def test_registry_retries_failed_stop_without_restarting_plugin():
    events = []
    plugin = FakePlugin("one", events, fail_stop=True)
    registry = PluginRegistry([plugin])
    registry.start_all()

    registry.stop_all()
    registry.start_all()
    plugin.fail_stop = False
    registry.stop_all()

    assert events == ["start:one", "stop:one", "stop:one"]


def test_registry_can_restart_plugins_after_stop():
    events = []
    registry = PluginRegistry([FakePlugin("one", events)])

    registry.start_all()
    registry.stop_all()
    registry.start_all()
    registry.stop_all()

    assert events == ["start:one", "stop:one", "start:one", "stop:one"]


def test_registry_collects_display_overrides_and_rejects_name_collisions():
    render = lambda *args: True
    calendar = DisplayOverride("calendar", render)
    transit = DisplayOverride("transit", render, aliases=("bus",))
    registry = PluginRegistry(
        [
            FakePlugin("calendar", [], display_overrides=(calendar,)),
            FakePlugin("base", [], display_overrides=(transit,)),
        ]
    )

    assert registry.display_overrides == (calendar, transit)

    duplicate = PluginRegistry(
        [
            FakePlugin("one", [], display_overrides=(transit,)),
            FakePlugin(
                "two",
                [],
                display_overrides=(DisplayOverride("bus", render),),
            ),
        ]
    )
    with pytest.raises(ValueError, match="already used"):
        duplicate.display_overrides


def test_real_plugins_implement_common_protocol():
    from breaking_news_plugin import BreakingNewsPlugin
    from calendar_plugin import CalendarPlugin
    from rss_plugin import RSSPlugin

    context = PluginContext(object(), ScreenArbiter(), threading.Lock())
    calendar_client = type(
        "CalendarClientStub", (), {"enabled": False, "timezone": None}
    )()
    rss_watcher = type("RSSWatcherStub", (), {"enabled": False})()
    news_watcher = type("NewsWatcherStub", (), {"enabled": False})()

    plugins = (
        CalendarPlugin(context, client=calendar_client),
        RSSPlugin(context, watcher=rss_watcher),
        BreakingNewsPlugin(context, watcher=news_watcher),
    )

    assert all(isinstance(plugin, DisplayPlugin) for plugin in plugins)
    assert plugins[0].display_overrides[0].module == "calendar"
    assert plugins[1].display_overrides == ()
    assert plugins[2].display_overrides == ()


def test_config_helpers_parse_values_and_validate_bounds():
    environ = {
        "ENABLED": " YES ",
        "COUNT": "4",
        "RATIO": "1.25",
        "OBJECT": '{"room": "office"}',
        "LIST": '["one", "two"]',
    }

    assert env_bool("ENABLED", environ=environ)
    assert env_int("COUNT", environ=environ, minimum=1, maximum=5) == 4
    assert env_float("RATIO", environ=environ) == 1.25
    assert env_json_object("OBJECT", environ=environ) == {"room": "office"}
    assert env_json_list("LIST", environ=environ) == ["one", "two"]
    assert env_int("MISSING", 7, environ=environ) == 7


@pytest.mark.parametrize(
    ("helper", "name", "value"),
    [
        (env_bool, "BOOL", "perhaps"),
        (env_int, "INT", "4.2"),
        (env_json_object, "JSON", "[]"),
        (env_json_list, "JSON", "not-json"),
    ],
)
def test_config_helpers_raise_contextual_errors(helper, name, value):
    with pytest.raises(ConfigError, match=name):
        helper(name, environ={name: value})


def test_periodic_rotation_claims_renders_dedupes_and_uses_view_settings():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)
    renders = []
    notifications = []
    key = {"value": 1}
    context = PluginContext(object(), arbiter, threading.Lock(), notifications.append)
    rotation = PeriodicRotatingScreen(
        context,
        [
            RotatingView(
                "one",
                lambda: renders.append("one"),
                duration_seconds=5,
                priority=10,
                render_key=lambda: key["value"],
            ),
            RotatingView(
                "two",
                lambda: renders.append("two"),
                duration_seconds=3,
                priority=20,
                exclusive=True,
            ),
        ],
        interval_seconds=10,
        clock=clock,
    )

    assert rotation.tick()
    assert not rotation.tick()
    assert arbiter.claim_for("one").priority == 10
    key["value"] = 2
    assert rotation.tick()

    clock.advance(5)
    assert rotation.tick()
    second_claim = arbiter.claim_for("two")
    assert second_claim.priority == 20
    assert second_claim.exclusive

    clock.advance(3)
    assert not rotation.tick()
    assert arbiter.active_owner() is None
    clock.advance(9)
    assert not rotation.tick()
    clock.advance(1)
    assert rotation.tick()
    assert renders == ["one", "one", "two", "one"]
    assert notifications == ["one", "one", "two", "one"]


def test_periodic_rotation_does_not_consume_preempted_view_duration():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)
    arbiter.claim("urgent", 99, 100)
    renders = []
    rotation = PeriodicRotatingScreen(
        PluginContext(object(), arbiter, threading.Lock()),
        [RotatingView("ambient", lambda: renders.append(True), 5, 10)],
        interval_seconds=10,
        clock=clock,
    )
    assert not rotation.tick()
    clock.advance(20)
    assert not rotation.tick()
    arbiter.release("urgent")
    assert rotation.tick()
    assert renders == [True]


def test_rotation_rechecks_ownership_after_taking_display_lock():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)
    rendered = []

    class PreemptingLock:
        def __enter__(self):
            arbiter.claim("urgent", 100, 10)

        def __exit__(self, *args):
            return False

    rotation = PeriodicRotatingScreen(
        PluginContext(object(), arbiter, PreemptingLock()),
        [RotatingView("normal", lambda: rendered.append(True), 5, 10)],
        interval_seconds=10,
        clock=clock,
    )

    assert not rotation.tick()
    assert rendered == []


def test_rotation_stop_releases_all_claims():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)
    rotation = PeriodicRotatingScreen(
        PluginContext(object(), arbiter, threading.Lock()),
        [RotatingView("owner", lambda: None, 5, 10)],
        interval_seconds=10,
        clock=clock,
    )
    rotation.tick()

    rotation.stop()

    assert not arbiter.has_claim("owner")


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
