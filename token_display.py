"""Compact e-paper views for Codex usage capacity and cost estimates."""

from __future__ import annotations

import os
from datetime import datetime

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


def _today_cost(snapshot: TokenUsageSnapshot) -> float:
    snapshot_date = snapshot.generated_at[:10]
    return next(
        (day.cost_usd for day in reversed(snapshot.daily) if day.date == snapshot_date),
        0,
    )


def _chart_slots(count: int, left: int, right: int):
    if count <= 0:
        return []
    gap = 2 if count <= 16 else 1
    span = right - left
    return [
        (
            round(left + span * index / count),
            round(left + span * (index + 1) / count) - gap,
        )
        for index in range(count)
    ]


def _cumulative_points(days, left: int, top: int, right: int, bottom: int):
    if not days:
        return []
    cumulative = []
    running_total = 0
    for day in days:
        running_total += max(0, day.cost_usd)
        cumulative.append(running_total)
    maximum = cumulative[-1] or 1
    slots = _chart_slots(len(days), left, right)
    return [(left, bottom)] + [
        (
            slots[index + 1][0] if index + 1 < len(slots) else right,
            round(bottom - (bottom - top) * value / maximum),
        )
        for index, value in enumerate(cumulative)
    ]


def draw_month_usage(epd, snapshot: TokenUsageSnapshot, set_base_image: bool = False):
    image, draw, black, white = _canvas(epd)
    fonts = _fonts()
    label, number, tiny, micro = fonts
    _header(draw, black, white, "MTD / EST. API VALUE", snapshot.stale, fonts)

    draw.text((7, 31), f"${snapshot.month_cost_usd:,.0f}", font=number, fill=black)
    draw.text((7, 58), "MONTH TO DATE", font=micro, fill=black)
    today_text = f"TODAY ${_today_cost(snapshot):,.0f}"
    today_width = draw.textbbox((0, 0), today_text, font=micro)[2]
    draw.text((243 - today_width, 58), today_text, font=micro, fill=black)
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
        for day, (left, right) in zip(
            days, _chart_slots(len(days), chart_left, chart_right)
        ):
            height = max(1, round((chart_bottom - chart_top) * day.cost_usd / maximum))
            draw.rectangle(
                (left, chart_bottom - height, right, chart_bottom - 1), fill=black
            )
        cumulative = _cumulative_points(
            days, chart_left, chart_top, chart_right, chart_bottom
        )
        draw.line(cumulative, fill=white, width=4, joint="curve")
        draw.line(cumulative, fill=black, width=2, joint="curve")
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
    if snapshot.primary.available:
        _limit_bar(draw, black, white, 31, "5 HOUR", snapshot.primary, fonts)
        _limit_bar(draw, black, white, 76, "WEEK", snapshot.secondary, fonts)
    else:
        # CodexBar omits rate windows that the service does not return. Keep
        # the same semantics here and let the weekly view breathe while the
        # temporary session-limit removal is active.
        _limit_bar(draw, black, white, 53, "WEEK", snapshot.secondary, fonts)
    _finish(epd, image, set_base_image)


def draw_usage_reset(epd, snapshot: TokenUsageSnapshot, set_base_image: bool = False):
    """Render a transient, glanceable state when live capacity resets."""

    image, draw, black, white = _canvas(epd)
    fonts = _fonts()
    label, number, tiny, micro = fonts
    _header(draw, black, white, "CAPACITY RESTORED", snapshot.stale, fonts)

    # An open ring reads as refresh/reset without relying on a font glyph that
    # may be unavailable on the Raspberry Pi image.
    draw.arc((10, 33, 78, 101), start=35, end=326, fill=black, width=7)
    draw.polygon(((69, 30), (81, 35), (71, 43)), fill=black)

    notice = snapshot.reset_notice
    if notice == "secondary":
        title = "WEEKLY LIMIT"
        window = snapshot.secondary
    elif notice == "both":
        title = "BOTH LIMITS"
        window = snapshot.primary
    else:
        title = "5 HOUR LIMIT"
        window = snapshot.primary

    draw.text((93, 32), title, font=micro, fill=black)
    draw.text((91, 45), "RESET", font=number, fill=black)
    if notice == "both":
        capacity = (
            f"5H {round(snapshot.primary.remaining_percent)}%  "
            f"WEEK {round(snapshot.secondary.remaining_percent)}%"
        )
        capacity_font = tiny
    else:
        capacity = f"{round(window.remaining_percent)}% AVAILABLE"
        capacity_font = label
    draw.text((92, 73), capacity, font=capacity_font, fill=black)

    draw.line((7, 106, 243, 106), fill=black, width=1)
    next_reset = _reset_label(window).replace("RESET", "NEXT", 1)
    draw.text((7, 109), next_reset, font=micro, fill=black)
    _finish(epd, image, set_base_image)
