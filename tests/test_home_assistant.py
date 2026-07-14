import json
import threading
from datetime import datetime, timezone

from display_adapter import MockDisplay
from home_assistant_display import (
    draw_home_assistant_screen,
    light_rows,
    resolve_entity_state,
)
from home_assistant_models import parse_config
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


def test_light_rows_show_seven_rooms_and_summarize_only_true_overflow():
    items = [(f"Room {index}", "on", False, None) for index in range(1, 10)]

    assert [item[0] for item in light_rows(items[:7])] == [
        f"Room {index}" for index in range(1, 8)
    ]
    assert [item[0] for item in light_rows(items)] == [
        "Room 1",
        "Room 2",
        "Room 3",
        "Room 4",
        "Room 5",
        "Room 6",
        "+3 more",
    ]


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
