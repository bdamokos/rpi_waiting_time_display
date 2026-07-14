"""Glanceable 250x120 Home Assistant cards."""

from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont

from font_utils import get_font_paths

ROTATION = int(os.getenv("screen_rotation", 90))
ACTIVE_STATES = {"on", "active", "detected", "true"}


def _fonts():
    try:
        paths = get_font_paths()
        return (
            ImageFont.truetype(paths["dejavu_bold"], 15),
            ImageFont.truetype(paths["dejavu"], 12),
            ImageFont.truetype(paths["dejavu_bold"], 24),
        )
    except OSError:
        font = ImageFont.load_default()
        return font, font, font


def _text(draw, value, font, width):
    value = " ".join(str(value).split())
    while value and draw.textbbox((0, 0), value, font=font)[2] > width:
        value = value[:-1]
    return value if value else "—"


def _value(entity, state):
    if state is None:
        return "—", True
    raw = state.attributes.get(entity.attribute) if entity.attribute else state.state
    stale = not state.available
    unit = (
        state.attributes.get("unit_of_measurement", "") if not entity.attribute else ""
    )
    try:
        raw = f"{float(raw):.1f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        raw = str(raw or "—")
    return f"{raw}{unit}", stale


def resolve_entity_state(entity, states):
    """Resolve a row, treating grouped binary entities as active when any is active."""
    candidates = [states.get(entity_id) for entity_id in entity.source_entity_ids]
    candidates = [state for state in candidates if state is not None]
    if not candidates:
        return None
    available = [state for state in candidates if state.available]
    usable = available or candidates
    active = [
        state
        for state in usable
        if state.state and state.state.strip().lower() in ACTIVE_STATES
    ]
    return max(active or usable, key=lambda state: state.received_monotonic)


def light_rows(items, limit=7):
    """Keep every active light visible, using a summary row only past capacity."""
    if len(items) <= limit:
        return items
    hidden = len(items) - (limit - 1)
    return items[: limit - 1] + [(f"+{hidden} more", "on", False, None)]


def screen_has_content(screen, states):
    if screen.type in {"lights", "climate"}:
        return any(
            state and state.available
            for state in (
                resolve_entity_state(item, states) for item in screen.entities
            )
        )
    return any(
        resolve_entity_state(item, states) is not None for item in screen.entities
    )


def draw_home_assistant_screen(
    epd, screen, states, *, stale_seconds=600, now_monotonic=None
):
    white = 1 if epd.is_bw_display else epd.WHITE
    black = 0 if epd.is_bw_display else epd.BLACK
    image = Image.new(
        "1" if epd.is_bw_display else "RGB", (epd.height, epd.width), white
    )
    draw = ImageDraw.Draw(image)
    heading, body, large = _fonts()
    draw.rectangle((0, 0, 249, 25), fill=black)
    draw.text(
        (7, 4),
        _text(draw, screen.title.upper(), heading, 228),
        font=heading,
        fill=white,
    )
    items = []
    for entity in screen.entities:
        state = resolve_entity_state(entity, states)
        value, stale = _value(entity, state)
        label = entity.label or entity.entity_id.split(".")[-1].replace("_", " ")
        if now_monotonic is not None and state is not None:
            stale = stale or now_monotonic - state.received_monotonic > stale_seconds
        items.append((label, value, stale, state))

    if screen.type == "lights":
        on = [
            (label, value, stale, state)
            for label, value, stale, state in items
            if state and str(state.state).lower() == "on"
        ]
        items = light_rows(on) if on else [("All lights", "off", False, None)]
    elif screen.type == "climate":
        active = [
            item
            for item in items
            if item[3]
            and str(item[3].attributes.get("hvac_action", "")).lower() == "heating"
        ]
        items = active or items

    if screen.type == "paired" and len(items) >= 2:
        for x, item in zip((8, 130), items[:2]):
            label, value, stale, _ = item
            draw.text((x, 36), _text(draw, label, body, 110), font=body, fill=black)
            draw.text((x, 60), _text(draw, value, large, 110), font=large, fill=black)
            if stale:
                draw.text((x, 96), "STALE", font=body, fill=black)
    else:
        compact = screen.type == "lights" and len(items) > 4
        rows = items if screen.type == "lights" else items[:4]
        for index, (label, value, stale, state) in enumerate(rows):
            y = 29 + index * 13 if compact else 32 + index * 21
            if screen.type == "climate" and state:
                current = state.attributes.get("current_temperature")
                target = state.attributes.get("temperature")
                if current is not None and target is not None:
                    value = f"{current} → {target}°"
            suffix = " !" if stale else ""
            draw.text((7, y), _text(draw, label, body, 145), font=body, fill=black)
            value_font = body if compact else heading
            rendered = _text(draw, f"{value}{suffix}", value_font, 88)
            width = draw.textbbox((0, 0), rendered, font=value_font)[2]
            draw.text((243 - width, y - 1), rendered, font=value_font, fill=black)

    image = image.rotate(ROTATION, expand=True)
    buffer = epd.getbuffer(image)
    if hasattr(epd, "displayPartial"):
        epd.displayPartial(buffer)
    else:
        epd.display(buffer)
    return image
