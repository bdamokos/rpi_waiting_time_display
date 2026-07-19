import json
import threading
from datetime import datetime, timezone

from display_adapter import MockDisplay
from home_assistant_display import (
    draw_home_assistant_screen,
    light_page,
    resolve_entity_state,
)
from home_assistant_models import TriggerConfig, parse_config
from home_assistant_plugin import HomeAssistantPlugin
from home_assistant_service import EntityState, HomeAssistantService
from plugins import PluginContext
from screen_arbiter import ScreenArbiter


def sample_config():
    return parse_config(
        {
            "interval_seconds": 10,
            "screens": [
                {
                    "id": "pair",
                    "type": "paired",
                    "title": "Pair",
                    "duration_seconds": 5,
                    "entities": [
                        {"entity_id": "sensor.left", "label": "Left"},
                        {"entity_id": "sensor.right", "label": "Right"},
                    ],
                }
            ],
            "triggers": [
                {
                    "entity_id": "binary_sensor.motion",
                    "screen_id": "pair",
                    "debounce_seconds": 5,
                    "duration_seconds": 8,
                    "priority": 70,
                }
            ],
        }
    )


def state(entity_id, value, received=0, attributes=None):
    return EntityState(
        entity_id,
        value,
        attributes or {},
        datetime.now(timezone.utc),
        received,
        value != "unavailable",
    )


class Response:
    def raise_for_status(self):
        pass

    def json(self):
        return [
            {
                "entity_id": "sensor.left",
                "state": "12",
                "attributes": {"unit_of_measurement": "g"},
            }
        ]


def test_rest_bootstrap_uses_bearer_and_filters_entities():
    calls = []
    service = HomeAssistantService(
        "http://ha.test",
        "secret",
        ["sensor.left"],
        request_get=lambda *a, **k: calls.append((a, k)) or Response(),
    )
    service.bootstrap()
    assert service.get("sensor.left").state == "12"
    assert calls[0][1]["headers"] == {"Authorization": "Bearer secret"}


class FakeSocket:
    def __init__(self):
        self.messages = iter(
            [
                json.dumps({"type": "auth_required"}),
                json.dumps({"type": "auth_ok"}),
                json.dumps(
                    {
                        "type": "event",
                        "event": {
                            "data": {
                                "new_state": {
                                    "entity_id": "sensor.left",
                                    "state": "9",
                                    "attributes": {},
                                }
                            }
                        },
                    }
                ),
            ]
        )
        self.sent = []

    def recv(self):
        return next(self.messages)

    def send(self, value):
        self.sent.append(json.loads(value))

    def close(self):
        pass


def test_websocket_auth_subscription_and_state_event():
    socket = FakeSocket()
    service = HomeAssistantService(
        "http://ha.test",
        "secret",
        ["sensor.left"],
        websocket_factory=lambda url: socket,
    )
    try:
        service._subscribe()
    except StopIteration:
        pass
    assert socket.sent[0] == {"type": "auth", "access_token": "secret"}
    assert socket.sent[1]["type"] == "subscribe_events"
    assert service.get("sensor.left").state == "9"


class FakeService:
    def __init__(self):
        self.states = {}
        self.listener = None

    def add_listener(self, listener):
        self.listener = listener

    def snapshot(self):
        return dict(self.states)

    def start(self):
        pass

    def stop(self):
        pass


def test_plugin_rotates_and_motion_transition_takes_over(monkeypatch):
    service = FakeService()
    service.states = {
        "sensor.left": state("sensor.left", "10"),
        "sensor.right": state("sensor.right", "20"),
    }
    renders = []
    monkeypatch.setattr(
        "home_assistant_plugin.draw_home_assistant_screen",
        lambda *a, **k: renders.append(a[1].screen_id),
    )
    context = PluginContext(MockDisplay(), ScreenArbiter(lambda: 0), threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=sample_config(), service=service, clock=lambda: 0
    )
    assert plugin.tick(0)
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )
    assert plugin.tick(0)
    assert context.arbiter.active_owner() == "ha-event:pair"
    assert renders == ["pair", "pair"]


def test_motion_can_require_continuous_activity_before_takeover():
    service = FakeService()
    service.states = {
        "sensor.left": state("sensor.left", "10"),
        "sensor.right": state("sensor.right", "20"),
        "binary_sensor.motion": state("binary_sensor.motion", "off"),
    }
    config_data = {
        "screens": [
            {
                "id": "pair",
                "entities": [{"entity_id": "sensor.left"}],
            }
        ],
        "triggers": [
            {
                "entity_id": "binary_sensor.motion",
                "screen_id": "pair",
                "active_for_seconds": 30,
                "duration_seconds": 8,
                "priority": 12,
            }
        ],
    }
    config = parse_config(config_data)
    context = PluginContext(MockDisplay(), ScreenArbiter(lambda: 0), threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: 0
    )

    service.states["binary_sensor.motion"] = state("binary_sensor.motion", "on")
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )

    plugin.tick(29.9)
    assert context.arbiter.active_owner() != "ha-event:pair"
    plugin.tick(30)
    assert context.arbiter.claim_for("ha-event:pair").priority == 12


def test_continuous_activity_takeover_is_cancelled_when_sensor_clears():
    service = FakeService()
    service.states = {
        "sensor.left": state("sensor.left", "10"),
        "binary_sensor.motion": state("binary_sensor.motion", "off"),
    }
    config = parse_config(
        {
            "screens": [{"id": "pair", "entities": [{"entity_id": "sensor.left"}]}],
            "triggers": [
                {
                    "entity_id": "binary_sensor.motion",
                    "screen_id": "pair",
                    "active_for_seconds": 30,
                }
            ],
        }
    )
    context = PluginContext(MockDisplay(), ScreenArbiter(lambda: 0), threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: 0
    )

    service.states["binary_sensor.motion"] = state("binary_sensor.motion", "on")
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )
    service.states["binary_sensor.motion"] = state("binary_sensor.motion", "off")
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "on"),
        state("binary_sensor.motion", "off"),
    )

    plugin.tick(30)
    assert context.arbiter.claim_for("ha-event:pair") is None


def test_stopping_plugin_cancels_pending_continuous_activity_takeover():
    service = FakeService()
    service.states = {
        "sensor.left": state("sensor.left", "10"),
        "binary_sensor.motion": state("binary_sensor.motion", "on"),
    }
    config = parse_config(
        {
            "screens": [{"id": "pair", "entities": [{"entity_id": "sensor.left"}]}],
            "triggers": [
                {
                    "entity_id": "binary_sensor.motion",
                    "screen_id": "pair",
                    "active_for_seconds": 30,
                }
            ],
        }
    )
    context = PluginContext(MockDisplay(), ScreenArbiter(lambda: 0), threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: 0
    )

    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )
    plugin.stop()
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )
    plugin.tick(30)

    assert context.arbiter.claim_for("ha-event:pair") is None


def test_trigger_active_for_seconds_defaults_to_immediate_and_is_non_negative():
    assert sample_config().triggers[0].active_for_seconds == 0
    assert sample_config().triggers[0].delay_seconds == 0

    config = parse_config(
        {
            "screens": [{"id": "pair", "entities": [{"entity_id": "sensor.left"}]}],
            "triggers": [
                {
                    "entity_id": "binary_sensor.motion",
                    "screen_id": "pair",
                    "active_for_seconds": -5,
                    "delay_seconds": -10,
                }
            ],
        }
    )
    assert config.triggers[0].active_for_seconds == 0
    assert config.triggers[0].delay_seconds == 0


def test_motion_can_queue_a_different_screen_after_delay_even_if_it_clears():
    now = [0.0]
    service = FakeService()
    service.states = {
        "sensor.left": state("sensor.left", "10"),
        "binary_sensor.motion": state("binary_sensor.motion", "off"),
    }
    config = parse_config(
        {
            "screens": [
                {
                    "id": "cat-bowls",
                    "entities": [{"entity_id": "sensor.left"}],
                }
            ],
            "triggers": [
                {
                    "entity_id": "binary_sensor.motion",
                    "screen_id": "cat-bowls",
                    "delay_seconds": 20,
                    "duration_seconds": 30,
                    "priority": 25,
                }
            ],
        }
    )
    arbiter = ScreenArbiter(lambda: now[0])
    context = PluginContext(MockDisplay(), arbiter, threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: now[0]
    )

    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "on"),
        state("binary_sensor.motion", "off"),
    )

    now[0] = 19.9
    plugin.tick()
    assert arbiter.claim_for("ha-event:cat-bowls") is None
    now[0] = 20
    plugin.tick()
    claim = arbiter.claim_for("ha-event:cat-bowls")
    assert claim is not None
    assert claim.priority == 25
    assert claim.expires_at == 50


def test_delayed_low_priority_takeover_gets_full_duration_after_claim_wins():
    now = [0.0]
    service = FakeService()
    service.states = {"sensor.left": state("sensor.left", "10")}
    config = parse_config(
        {
            "screens": [
                {
                    "id": "cat-bowls",
                    "entities": [{"entity_id": "sensor.left"}],
                }
            ],
            "triggers": [
                {
                    "entity_id": "binary_sensor.motion",
                    "screen_id": "cat-bowls",
                    "delay_seconds": 20,
                    "duration_seconds": 30,
                    "priority": 25,
                }
            ],
        }
    )
    arbiter = ScreenArbiter(lambda: now[0])
    context = PluginContext(MockDisplay(), arbiter, threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: now[0]
    )
    assert arbiter.claim("current-screen", 80, 25)
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )

    now[0] = 20
    assert not plugin.tick()
    assert arbiter.active_owner() == "current-screen"
    now[0] = 25
    plugin.tick()
    assert arbiter.active_owner() == "ha-event:cat-bowls"
    assert arbiter.claim_for("ha-event:cat-bowls").expires_at == 55
    now[0] = 54.9
    plugin.tick()
    assert arbiter.active_owner() == "ha-event:cat-bowls"
    now[0] = 55
    plugin.tick()
    assert arbiter.active_owner() != "ha-event:cat-bowls"


def test_multiple_target_takeovers_wait_in_priority_order():
    now = [0.0]
    service = FakeService()
    service.states = {
        "sensor.first": state("sensor.first", "1"),
        "sensor.second": state("sensor.second", "2"),
    }
    config = parse_config(
        {
            "screens": [
                {"id": "first", "entities": [{"entity_id": "sensor.first"}]},
                {"id": "second", "entities": [{"entity_id": "sensor.second"}]},
            ],
            "triggers": [
                {
                    "entity_id": "binary_sensor.urgent",
                    "screen_id": "first",
                    "duration_seconds": 10,
                    "priority": 80,
                },
                {
                    "entity_id": "binary_sensor.informational",
                    "screen_id": "second",
                    "duration_seconds": 30,
                    "priority": 25,
                },
            ],
        }
    )
    arbiter = ScreenArbiter(lambda: now[0])
    context = PluginContext(MockDisplay(), arbiter, threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: now[0]
    )

    service.listener(
        "binary_sensor.urgent",
        state("binary_sensor.urgent", "off"),
        state("binary_sensor.urgent", "on"),
    )
    plugin.tick()
    now[0] = 1
    service.listener(
        "binary_sensor.informational",
        state("binary_sensor.informational", "off"),
        state("binary_sensor.informational", "on"),
    )
    plugin.tick()
    assert arbiter.active_owner() == "ha-event:first"
    assert arbiter.claim_for("ha-event:second") is not None

    now[0] = 10
    plugin.tick()
    assert arbiter.active_owner() == "ha-event:second"
    assert arbiter.claim_for("ha-event:second").expires_at == 40


def test_lower_priority_retrigger_cannot_downgrade_same_target_takeover():
    now = [0.0]
    service = FakeService()
    service.states = {"sensor.bowls": state("sensor.bowls", "10")}
    config = parse_config(
        {
            "screens": [
                {"id": "cat-bowls", "entities": [{"entity_id": "sensor.bowls"}]}
            ],
            "triggers": [
                {
                    "entity_id": "binary_sensor.cat_present",
                    "screen_id": "cat-bowls",
                    "priority": 70,
                },
                {
                    "entity_id": "binary_sensor.kitchen_motion",
                    "screen_id": "cat-bowls",
                    "priority": 25,
                },
            ],
        }
    )
    arbiter = ScreenArbiter(lambda: now[0])
    context = PluginContext(MockDisplay(), arbiter, threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: now[0]
    )
    service.listener(
        "binary_sensor.cat_present",
        state("binary_sensor.cat_present", "off"),
        state("binary_sensor.cat_present", "on"),
    )
    plugin.tick()

    now[0] = 1
    service.listener(
        "binary_sensor.kitchen_motion",
        state("binary_sensor.kitchen_motion", "off"),
        state("binary_sensor.kitchen_motion", "on"),
    )
    plugin.tick()

    assert arbiter.active_owner() == "ha-event:cat-bowls"
    assert arbiter.claim_for("ha-event:cat-bowls").priority == 70


def test_stopping_plugin_cancels_delayed_takeover():
    service = FakeService()
    service.states = {"sensor.left": state("sensor.left", "10")}
    config = parse_config(
        {
            "screens": [{"id": "pair", "entities": [{"entity_id": "sensor.left"}]}],
            "triggers": [
                {
                    "entity_id": "binary_sensor.motion",
                    "screen_id": "pair",
                    "delay_seconds": 20,
                }
            ],
        }
    )
    context = PluginContext(MockDisplay(), ScreenArbiter(lambda: 0), threading.Lock())
    plugin = HomeAssistantPlugin(
        context, config=config, service=service, clock=lambda: 0
    )
    service.listener(
        "binary_sensor.motion",
        state("binary_sensor.motion", "off"),
        state("binary_sensor.motion", "on"),
    )

    plugin.stop()
    plugin.tick(20)

    assert context.arbiter.claim_for("ha-event:pair") is None


def test_trigger_config_preserves_existing_positional_argument_order():
    trigger = TriggerConfig(
        "binary_sensor.motion",
        "pair",
        ("on",),
        12,
        45,
        70,
    )

    assert trigger.debounce_seconds == 12
    assert trigger.duration_seconds == 45
    assert trigger.priority == 70
    assert trigger.active_for_seconds == 0
    assert trigger.delay_seconds == 0


def test_grouped_binary_entity_is_active_when_either_or_both_members_are_active():
    config = parse_config(
        {
            "screens": [
                {
                    "id": "motion",
                    "type": "entities",
                    "entities": [
                        {
                            "entity_ids": [
                                "binary_sensor.hall_eve",
                                "binary_sensor.hall_hue",
                            ],
                            "label": "Hall",
                        }
                    ],
                }
            ]
        }
    )
    entity = config.screens[0].entities[0]

    for eve, hue, expected in (
        ("off", "off", "off"),
        ("on", "off", "on"),
        ("off", "on", "on"),
        ("on", "on", "on"),
    ):
        states = {
            "binary_sensor.hall_eve": state("binary_sensor.hall_eve", eve, 1),
            "binary_sensor.hall_hue": state("binary_sensor.hall_hue", hue, 2),
        }
        assert resolve_entity_state(entity, states).state == expected


def test_plugin_subscribes_to_every_group_member(monkeypatch):
    monkeypatch.setenv("home_assistant_enabled", "true")
    monkeypatch.setenv("home_assistant_url", "http://ha.test")
    monkeypatch.setenv("home_assistant_token", "secret")
    monkeypatch.setenv(
        "home_assistant_config",
        json.dumps(
            {
                "screens": [
                    {
                        "id": "motion",
                        "entities": [
                            {
                                "entity_ids": [
                                    "binary_sensor.hall_eve",
                                    "binary_sensor.hall_hue",
                                ]
                            }
                        ],
                    }
                ]
            }
        ),
    )
    context = PluginContext(MockDisplay(), ScreenArbiter(), threading.Lock())

    plugin = HomeAssistantPlugin.from_env(context)

    assert plugin.service.entity_ids == {
        "binary_sensor.hall_eve",
        "binary_sensor.hall_hue",
    }


def test_grouped_entity_parser_handles_null_and_rejects_invalid_types():
    config = parse_config(
        {
            "screens": [
                {
                    "id": "motion",
                    "entities": [
                        {"entity_id": "binary_sensor.hall", "entity_ids": None}
                    ],
                }
            ]
        }
    )
    assert config.screens[0].entities[0].source_entity_ids == ("binary_sensor.hall",)

    try:
        parse_config(
            {
                "screens": [
                    {
                        "id": "motion",
                        "entities": [{"entity_ids": 123}],
                    }
                ]
            }
        )
    except ValueError as exc:
        assert str(exc) == "Home Assistant entity_ids must be a list"
    else:
        raise AssertionError("invalid entity_ids should be rejected")


def test_light_rows_paginate_at_the_readable_four_row_size():
    items = [(f"Room {index}", "on", False, None) for index in range(1, 8)]

    assert [item[0] for item in light_page(items, 0)] == [
        "Room 1",
        "Room 2",
        "Room 3",
        "Room 4",
    ]
    assert [item[0] for item in light_page(items, 1)] == [
        "Room 5",
        "Room 6",
        "Room 7",
    ]
    assert light_page(items, 2) == light_page(items, 0)


def test_lights_card_switches_pages_after_configured_read_time(monkeypatch):
    service = FakeService()
    service.states = {
        f"light.room_{index}": state(f"light.room_{index}", "on") for index in range(5)
    }
    config = parse_config(
        {
            "screens": [
                {
                    "id": "lights",
                    "type": "lights",
                    "duration_seconds": 30,
                    "page_seconds": 15,
                    "entities": [
                        {"entity_id": entity_id} for entity_id in service.states
                    ],
                }
            ]
        }
    )
    pages = []
    monkeypatch.setattr(
        "home_assistant_plugin.draw_home_assistant_screen",
        lambda *args, **kwargs: pages.append(kwargs["page"]),
    )
    context = PluginContext(MockDisplay(), ScreenArbiter(lambda: 0), threading.Lock())
    plugin = HomeAssistantPlugin(context, config=config, service=service)

    assert plugin.tick(0)
    assert not plugin.tick(14)
    assert plugin.tick(15)
    assert pages == [0, 1]


def test_unavailable_state_preserves_last_good_value():
    service = HomeAssistantService("http://ha.test", "secret", ["sensor.left"])
    service._store({"entity_id": "sensor.left", "state": "11", "attributes": {}}, False)
    service._store(
        {"entity_id": "sensor.left", "state": "unavailable", "attributes": {}}, False
    )
    result = service.get("sensor.left")
    assert result.state == "11" and not result.available


def test_all_renderers_are_null_safe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    epd = MockDisplay()
    for kind in ("temperatures", "lights", "climate", "paired", "entities"):
        config = parse_config(
            {
                "screens": [
                    {
                        "id": kind,
                        "type": kind,
                        "entities": [
                            {"entity_id": "sensor.missing"},
                            {"entity_id": "sensor.other"},
                        ],
                    }
                ]
            }
        )
        image = draw_home_assistant_screen(epd, config.screens[0], {})
        assert image.size == (120, 250)
