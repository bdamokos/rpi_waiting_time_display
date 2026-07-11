"""Compact e-paper views for upcoming calendar events."""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from calendar_service import CalendarEvent
from display_adapter import return_display_lock
from font_utils import get_font_paths

display_lock = return_display_lock()
DISPLAY_SCREEN_ROTATION = int(os.getenv("screen_rotation", 90))


def _fonts():
    paths = get_font_paths()
    try:
        return (
            ImageFont.truetype(paths["dejavu_bold"], 13),
            ImageFont.truetype(paths["dejavu_bold"], 15),
            ImageFont.truetype(paths["dejavu"], 10),
            ImageFont.truetype(paths["dejavu_bold"], 27),
        )
    except OSError:
        fallback = ImageFont.load_default()
        return fallback, fallback, fallback, fallback


def _canvas(epd):
    white = epd.WHITE if not epd.is_bw_display else 1
    black = epd.BLACK if not epd.is_bw_display else 0
    image = Image.new(
        "1" if epd.is_bw_display else "RGB",
        (epd.height, epd.width),
        white,
    )
    return image, ImageDraw.Draw(image), black


def _finish(epd, image, set_base_image: bool):
    image = image.rotate(DISPLAY_SCREEN_ROTATION, expand=True)
    with display_lock:
        buffer = epd.getbuffer(image)
        if hasattr(epd, "displayPartial"):
            if set_base_image and hasattr(epd, "displayPartBaseImage"):
                epd.init()
                epd.displayPartBaseImage(buffer)
            else:
                epd.displayPartial(buffer)
        else:
            epd.display(buffer)


def _ellipsize(draw, text: str, font, max_width: int) -> str:
    text = " ".join(text.split())
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    while text and draw.textbbox((0, 0), f"{text}…", font=font)[2] > max_width:
        text = text[:-1]
    return f"{text.rstrip()}…" if text else "…"


def _wrap_two_lines(draw, text: str, font, max_width: int):
    words = " ".join(text.split()).split(" ")
    lines = []
    while words and len(lines) < 2:
        current = ""
        while words:
            candidate = f"{current} {words[0]}".strip()
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                break
            current = candidate
            words.pop(0)
            if draw.textbbox((0, 0), current, font=font)[2] > max_width:
                current = _ellipsize(draw, current, font, max_width)
                break
        if len(lines) == 1 and words:
            current = _ellipsize(
                draw,
                f"{current} {' '.join(words)}",
                font,
                max_width,
            )
            words.clear()
        if current:
            lines.append(current)
    return lines[:2]


def draw_upcoming_event(
    epd,
    event: CalendarEvent,
    now: datetime,
    *,
    set_base_image: bool = False,
):
    image, draw, black = _canvas(epd)
    header, title_font, tiny, countdown_font = _fonts()
    status = "STALE" if event.stale else event.start.strftime("%H:%M")
    draw.text((7, 5), "CALENDAR", font=header, fill=black)
    status_width = draw.textbbox((0, 0), status, font=tiny)[2]
    draw.text((243 - status_width, 7), status, font=tiny, fill=black)
    draw.line((7, 24, 243, 24), fill=black, width=1)

    for index, line in enumerate(_wrap_two_lines(draw, event.summary, title_font, 236)):
        draw.text((7, 29 + index * 17), line, font=title_font, fill=black)
    if event.location:
        location = _ellipsize(draw, event.location, tiny, 236)
        draw.text((7, 65), location, font=tiny, fill=black)

    seconds = max(0, (event.start - now).total_seconds())
    minutes = math.ceil(seconds / 60)
    countdown = "STARTS NOW" if minutes == 0 else f"IN {minutes} MIN"
    width = draw.textbbox((0, 0), countdown, font=countdown_font)[2]
    draw.text(((250 - width) // 2, 82), countdown, font=countdown_font, fill=black)
    _finish(epd, image, set_base_image)


def _event_time_label(event: CalendarEvent, now: datetime) -> str:
    if event.start.date() == now.date():
        day = "TODAY"
    elif event.start.date() == (now.date() + timedelta(days=1)):
        day = "TOM"
    else:
        day = event.start.strftime("%a").upper()
    return f"{day} ALL" if event.all_day else f"{day} {event.start:%H:%M}"


def draw_calendar_agenda(
    epd,
    events: Iterable[CalendarEvent],
    now: datetime,
    *,
    set_base_image: bool = False,
):
    events = list(events)
    image, draw, black = _canvas(epd)
    header, title_font, tiny, _ = _fonts()
    status = "STALE" if any(event.stale for event in events) else now.strftime("%H:%M")
    draw.text((7, 5), "UPCOMING", font=header, fill=black)
    status_width = draw.textbbox((0, 0), status, font=tiny)[2]
    draw.text((243 - status_width, 7), status, font=tiny, fill=black)
    draw.line((7, 24, 243, 24), fill=black, width=1)

    for index, event in enumerate(events[:4]):
        y = 29 + index * 23
        label = _event_time_label(event, now)
        draw.text((7, y + 2), label, font=tiny, fill=black)
        title = _ellipsize(draw, event.summary, title_font, 160)
        draw.text((82, y), title, font=title_font, fill=black)
        if index < min(len(events), 4) - 1:
            draw.line((7, y + 20, 243, y + 20), fill=black, width=1)
    _finish(epd, image, set_base_image)
