"""Compact e-paper views for Codex usage capacity and cost estimates."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from display_adapter import return_display_lock
from font_utils import get_font_paths
from token_usage import RateWindow, TokenUsageSnapshot

display_lock = return_display_lock()
DISPLAY_SCREEN_ROTATION = int(os.getenv("screen_rotation", 90))


def _fonts():
    paths = get_font_paths()
    try:
        return (
            ImageFont.truetype(paths["dejavu_bold"], 14),
            ImageFont.truetype(paths["dejavu_bold"], 22),
            ImageFont.truetype(paths["dejavu"], 11),
            ImageFont.truetype(paths["dejavu_bold"], 10),
        )
    except OSError:
        fallback = ImageFont.load_default()
        return fallback, fallback, fallback, fallback


def _canvas(epd):
    white = epd.WHITE if not epd.is_bw_display else 1
    black = epd.BLACK if not epd.is_bw_display else 0
    image = Image.new(
        "1" if epd.is_bw_display else "RGB", (epd.height, epd.width), white
    )
    return image, ImageDraw.Draw(image), black, white


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


def _reset_badge(draw, black, white, count: int, font):
    if count <= 0:
        return
    text = "9+" if count > 9 else str(count)
    # The display edge clips the circle into an app-style corner badge.
    draw.ellipse((227, -10, 261, 24), fill=black)
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        (241 - width // 2, 8 - height // 2 - bounds[1]),
        text,
        font=font,
        fill=white,
    )


def _header(
    draw,
    black,
    white,
    title: str,
    stale: bool,
    fonts,
    resets_available: int = 0,
):
    label, _, tiny, micro = fonts
    draw.text((7, 5), "CODEX", font=label, fill=black)
    draw.line((55, 13, 67, 13), fill=black, width=1)
    draw.text((72, 6), title, font=micro, fill=black)
    status = "STALE" if stale else datetime.now().strftime("%H:%M")
    width = draw.textbbox((0, 0), status, font=tiny)[2]
    status_right = 222 if resets_available else 243
    draw.text((status_right - width, 6), status, font=tiny, fill=black)
    _reset_badge(draw, black, white, resets_available, micro)
    draw.line((7, 24, 243, 24), fill=black, width=1)


def _compact_tokens(value: int) -> str:
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.0f}M"
    if value >= 1_000:
        return f"{value / 1_000:.0f}K"
    return str(value)


def draw_month_usage(epd, snapshot: TokenUsageSnapshot, set_base_image: bool = False):
    image, draw, black, white = _canvas(epd)
    fonts = _fonts()
    label, number, tiny, micro = fonts
    _header(draw, black, white, "MTD / EST. API VALUE", snapshot.stale, fonts)

    draw.text((7, 31), f"${snapshot.month_cost_usd:,.0f}", font=number, fill=black)
    draw.text((7, 58), "MONTH TO DATE", font=micro, fill=black)
    token_text = f"{_compact_tokens(snapshot.month_tokens)} TOKENS"
    token_width = draw.textbbox((0, 0), token_text, font=tiny)[2]
    draw.text((243 - token_width, 38), token_text, font=tiny, fill=black)

    days = snapshot.daily[-31:]
    chart_left, chart_top, chart_right, chart_bottom = 7, 73, 243, 109
    draw.line(
        (chart_left, chart_bottom, chart_right, chart_bottom), fill=black, width=1
    )
    if days:
        maximum = max(day.cost_usd for day in days) or 1
        gap = 2 if len(days) <= 16 else 1
        width = max(2, (chart_right - chart_left - gap * (len(days) - 1)) // len(days))
        for index, day in enumerate(days):
            height = max(1, round((chart_bottom - chart_top) * day.cost_usd / maximum))
            x = chart_left + index * (width + gap)
            draw.rectangle(
                (x, chart_bottom - height, x + width - 1, chart_bottom - 1), fill=black
            )
        first = days[0].date[-2:].lstrip("0")
        last = days[-1].date[-2:].lstrip("0")
        draw.text((chart_left, 109), first, font=micro, fill=black)
        last_width = draw.textbbox((0, 0), last, font=micro)[2]
        draw.text((chart_right - last_width, 109), last, font=micro, fill=black)
    _finish(epd, image, set_base_image)


def _reset_label(window: RateWindow) -> str:
    if not window.resets_at:
        return "RESET --"
    try:
        parsed = datetime.fromisoformat(
            window.resets_at.replace("Z", "+00:00")
        ).astimezone()
        return f"RESET {parsed.strftime('%a %H:%M').upper()}"
    except ValueError:
        return "RESET --"


def _limit_bar(draw, black, white, y: int, title: str, window: RateWindow, fonts):
    _, number, tiny, micro = fonts
    remaining = round(window.remaining_percent)
    draw.text((7, y), title, font=micro, fill=black)
    value = f"{remaining}%"
    value_width = draw.textbbox((0, 0), value, font=number)[2]
    draw.text((243 - value_width, y - 6), value, font=number, fill=black)
    draw.text((7, y + 14), _reset_label(window), font=tiny, fill=black)
    bar_y = y + 30
    draw.rectangle((7, bar_y, 243, bar_y + 9), outline=black, width=1)
    fill_width = round(234 * remaining / 100)
    if fill_width:
        draw.rectangle((8, bar_y + 1, 8 + fill_width, bar_y + 8), fill=black)


def draw_usage_limits(epd, snapshot: TokenUsageSnapshot, set_base_image: bool = False):
    image, draw, black, white = _canvas(epd)
    fonts = _fonts()
    _header(
        draw,
        black,
        white,
        "CAPACITY REMAINING",
        snapshot.stale,
        fonts,
        resets_available=snapshot.resets_available,
    )
    _limit_bar(draw, black, white, 31, "5 HOUR", snapshot.primary, fonts)
    _limit_bar(draw, black, white, 76, "WEEK", snapshot.secondary, fonts)
    _finish(epd, image, set_base_image)
