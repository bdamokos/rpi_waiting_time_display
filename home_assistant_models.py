"""Immutable public configuration for Home Assistant display screens."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class EntityConfig:
    entity_id: str
    label: str = ""
    attribute: str = ""
    entity_ids: Tuple[str, ...] = ()

    @property
    def source_entity_ids(self) -> Tuple[str, ...]:
        return self.entity_ids or (self.entity_id,)


@dataclass(frozen=True)
class ScreenConfig:
    screen_id: str
    type: str
    title: str
    entities: Tuple[EntityConfig, ...]
    duration_seconds: float = 30.0
    page_seconds: float = 15.0
    priority: int = 18


@dataclass(frozen=True)
class TriggerConfig:
    entity_id: str
    screen_id: str
    active_states: Tuple[str, ...] = ("on", "active", "detected", "true")
    debounce_seconds: float = 10.0
    duration_seconds: float = 30.0
    priority: int = 65
    active_for_seconds: float = 0.0


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
        entities = []
        for entity in item.get("entities", []):
            raw_source_ids = entity.get("entity_ids") or ()
            if not isinstance(raw_source_ids, (list, tuple)):
                raise ValueError("Home Assistant entity_ids must be a list")
            source_ids = tuple(dict.fromkeys(str(value) for value in raw_source_ids))
            entity_id = str(
                entity.get("entity_id") or (source_ids[0] if source_ids else "")
            )
            if not entity_id:
                raise ValueError(
                    "Home Assistant entities require entity_id or entity_ids"
                )
            entities.append(
                EntityConfig(
                    entity_id,
                    str(entity.get("label", "")),
                    str(entity.get("attribute", "")),
                    source_ids,
                )
            )
        entities = tuple(entities)
        if not entities:
            raise ValueError("Home Assistant screens require entities")
        screens.append(
            ScreenConfig(
                str(item["id"]),
                kind,
                str(item.get("title", item["id"])),
                entities,
                float(item.get("duration_seconds", 30)),
                max(1.0, float(item.get("page_seconds", 15))),
                int(item.get("priority", 18)),
            )
        )
    ids = {screen.screen_id for screen in screens}
    if len(ids) != len(screens):
        raise ValueError("duplicate Home Assistant screen id")
    triggers = tuple(
        TriggerConfig(
            entity_id=str(item["entity_id"]),
            screen_id=str(item["screen_id"]),
            active_states=tuple(
                str(value).lower()
                for value in item.get(
                    "active_states", ("on", "active", "detected", "true")
                )
            ),
            debounce_seconds=float(item.get("debounce_seconds", 10)),
            duration_seconds=float(item.get("duration_seconds", 30)),
            priority=int(item.get("priority", 65)),
            active_for_seconds=max(0.0, float(item.get("active_for_seconds", 0))),
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
