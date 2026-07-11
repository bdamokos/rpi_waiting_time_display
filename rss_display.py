"""Compact RSS and Nitter cards for a 250x120 e-paper canvas."""

from __future__ import annotations

import io
import os
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from display_adapter import return_display_lock
from font_utils import get_font_paths

display_lock = return_display_lock()
DISPLAY_SCREEN_ROTATION = int(os.getenv("screen_rotation", "90"))


@lru_cache(maxsize=1)
def _fonts():
    paths = get_font_paths()
    try:
        return (
            ImageFont.truetype(paths["dejavu_bold"], 12),
            ImageFont.truetype(paths["dejavu_bold"], 14),
            ImageFont.truetype(paths["dejavu"], 11),
            ImageFont.truetype(paths["dejavu"], 9),
        )
    except OSError:
        fallback = ImageFont.load_default()
        return fallback, fallback, fallback, fallback


def _ellipsize(draw, text, font, width):
    text = " ".join(text.split())
    if draw.textbbox((0, 0), text, font=font)[2] <= width:
        return text
    while text and draw.textbbox((0, 0), text + "…", font=font)[2] > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(draw, text, font, width, lines):
    words = " ".join(text.split()).split()
    output = []
    while words and len(output) < lines:
        line = ""
        while words:
            candidate = f"{line} {words[0]}".strip()
            if line and draw.textbbox((0, 0), candidate, font=font)[2] > width:
                break
            line = candidate
            words.pop(0)
        if len(output) == lines - 1 and words:
            line = _ellipsize(draw, f"{line} {' '.join(words)}", font, width)
            words.clear()
        output.append(line)
    return output


def _finish(epd, image, set_base_image):
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


def draw_feed_entry(epd, entry, *, avatar_bytes=None, set_base_image=False):
    white = epd.WHITE if not epd.is_bw_display else 1
    black = epd.BLACK if not epd.is_bw_display else 0
    image = Image.new(
        "1" if epd.is_bw_display else "RGB", (epd.height, epd.width), white
    )
    draw = ImageDraw.Draw(image)
    header, title_font, body_font, tiny = _fonts()
    is_tweet = entry.kind == "nitter"
    label = (
        "NEW POST"
        if is_tweet
        else _ellipsize(draw, entry.publication.upper(), header, 180)
    )
    draw.text((7, 5), label, font=header, fill=black)
    time_label = (
        entry.published.astimezone().strftime("%H:%M") if entry.published else "RSS"
    )
    time_width = draw.textbbox((0, 0), time_label, font=tiny)[2]
    draw.text((243 - time_width, 7), time_label, font=tiny, fill=black)
    draw.line((7, 23, 243, 23), fill=black, width=1)

    left = 7
    if is_tweet and avatar_bytes:
        try:
            avatar = Image.open(io.BytesIO(avatar_bytes)).convert("L")
            avatar = ImageOps.fit(avatar, (38, 38)).convert(image.mode)
            image.paste(avatar, (7, 30))
            left = 52
        except (OSError, ValueError):
            pass
    if is_tweet:
        author = entry.author or entry.publication
        identity = f"{author}  {entry.handle}".strip()
        draw.text(
            (left, 29),
            _ellipsize(draw, identity, title_font, 243 - left),
            font=title_font,
            fill=black,
        )
        y, max_lines = 48, 4
        width = 243 - left if left > 7 else 236
        for index, line in enumerate(
            _wrap(draw, entry.title, body_font, width, max_lines)
        ):
            draw.text((left, y + index * 14), line, font=body_font, fill=black)
    else:
        for index, line in enumerate(_wrap(draw, entry.title, title_font, 236, 4)):
            draw.text((7, 31 + index * 18), line, font=title_font, fill=black)
        if entry.author:
            draw.text(
                (7, 104),
                _ellipsize(draw, entry.author, tiny, 236),
                font=tiny,
                fill=black,
            )
    _finish(epd, image, set_base_image)
