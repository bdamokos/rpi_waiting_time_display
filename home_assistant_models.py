"""Immutable public configuration for Home Assistant display screens."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class EntityConfig:
    entity_id: str
    label: str = ""
    attribute: str = ""


@dataclass(frozen=True)
class ScreenConfig:
    screen_id: str
    type: str
    title: str
    entities: Tuple[EntityConfig, ...]
    duration_seconds: float = 30.0
    priority: int = 18


@dataclass(frozen=True)
class TriggerConfig:
    entity_id: str
    screen_id: str
    active_states: Tuple[str, ...] = ("on", "active", "detected", "true")
    debounce_seconds: float = 10.0
    duration_seconds: float = 30.0
    priority: int = 65


@dataclass(frozen=True)
class HomeAssistantConfig:
    screens: Tuple[ScreenConfig, ...]
    triggers: Tuple[TriggerConfig, ...] = ()
    interval_seconds: float = 180.0
    stale_seconds: float = 600.0


def parse_config(data) -> HomeAssistantConfig:
    screens = []
    known = {"temperatures", "lights", "climate", "paired", "entities"}
    for item in data.get("screens", []):
        kind = str(item.get("type", "entities")).lower()
        if kind not in known:
            raise ValueError(f"unknown Home Assistant screen type: {kind}")
        entities = tuple(
            EntityConfig(
                str(entity["entity_id"]),
                str(entity.get("label", "")),
                str(entity.get("attribute", "")),
            )
            for entity in item.get("entities", [])
        )
        if not entities:
            raise ValueError("Home Assistant screens require entities")
        screens.append(
            ScreenConfig(
                str(item["id"]),
                kind,
                str(item.get("title", item["id"])),
                entities,
                float(item.get("duration_seconds", 30)),
                int(item.get("priority", 18)),
            )
        )
    ids = {screen.screen_id for screen in screens}
    if len(ids) != len(screens):
        raise ValueError("duplicate Home Assistant screen id")
    triggers = tuple(
        TriggerConfig(
            str(item["entity_id"]),
            str(item["screen_id"]),
            tuple(
                str(value).lower()
                for value in item.get(
                    "active_states", ("on", "active", "detected", "true")
                )
            ),
            float(item.get("debounce_seconds", 10)),
            float(item.get("duration_seconds", 30)),
            int(item.get("priority", 65)),
        )
        for item in data.get("triggers", [])
    )
    if any(trigger.screen_id not in ids for trigger in triggers):
        raise ValueError("Home Assistant trigger references an unknown screen")
    return HomeAssistantConfig(
        tuple(screens),
        triggers,
        float(data.get("interval_seconds", 180)),
        float(data.get("stale_seconds", 600)),
    )
