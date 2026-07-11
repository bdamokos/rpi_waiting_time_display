"""Sharp 1-bit YNAB budget views for the 250x120 e-paper canvas."""

from __future__ import annotations

import calendar
import os
from datetime import datetime
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from display_adapter import return_display_lock
from font_utils import get_font_paths
from ynab_budget import YnabSnapshot

display_lock = return_display_lock()
DISPLAY_SCREEN_ROTATION = int(os.getenv("screen_rotation", "90"))


@lru_cache(maxsize=1)
def _fonts():
    paths = get_font_paths()
    try:
        return (
            ImageFont.truetype(paths["dejavu_bold"], 13),
            ImageFont.truetype(paths["dejavu_bold"], 25),
            ImageFont.truetype(paths["dejavu_bold"], 10),
            ImageFont.truetype(paths["dejavu"], 9),
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


def _header(draw, black, snapshot, title, fonts):
    header, _, tiny, micro = fonts
    draw.text((7, 5), "YNAB", font=header, fill=black)
    draw.text((52, 7), "/", font=micro, fill=black)
    draw.text((64, 7), title, font=micro, fill=black)
    status = "STALE" if snapshot.stale else datetime.now().strftime("%H:%M")
    width = draw.textbbox((0, 0), status, font=tiny)[2]
    draw.text((243 - width, 6), status, font=tiny, fill=black)
    draw.line((7, 24, 243, 24), fill=black, width=1)


def _money(snapshot, value, decimals=0):
    return f"{snapshot.currency_symbol}{value:,.{decimals}f}"


def _bar(draw, black, x, y, width, fraction):
    draw.rectangle((x, y, x + width, y + 9), outline=black, width=1)
    fill = round((width - 3) * max(0, min(1, fraction)))
    if fill:
        draw.rectangle((x + 2, y + 2, x + 1 + fill, y + 7), fill=black)


def _names(env_name, default):
    return [
        item.strip()
        for item in os.getenv(env_name, default).split(",")
        if item.strip()
    ]


def _spending_categories(snapshot):
    excluded = set(
        _names(
            "ynab_non_spending_groups",
            "Savings Goals,Investments,Rainy Day Funds",
        )
    )
    return [
        item
        for item in snapshot.categories
        if item.assigned > 0 and item.group not in excluded
    ]


def _right(draw, text, y, font, black):
    width = draw.textbbox((0, 0), text, font=font)[2]
    draw.text((243 - width, y), text, font=font, fill=black)


def draw_ynab_view(
    epd, snapshot: YnabSnapshot, view: str, now=None, set_base_image=False
):
    now = now or datetime.now()
    image, draw, black, white = _canvas(epd)
    fonts = _fonts()
    if view == "daily":
        _draw_daily(draw, black, snapshot, now, fonts)
    elif view == "active":
        _draw_active(draw, black, snapshot, fonts)
    elif view == "funding":
        _draw_funding(draw, black, snapshot, fonts)
    elif view == "exception":
        _draw_exception(draw, black, white, snapshot, fonts)
    else:
        _draw_month(draw, black, snapshot, fonts)
    _finish(epd, image, set_base_image)


def _draw_month(draw, black, snapshot, fonts):
    header, number, tiny, micro = fonts
    _header(draw, black, snapshot, "MONTH PLAN", fonts)
    categories = _spending_categories(snapshot)
    assigned = sum(item.assigned for item in categories)
    spent = sum(item.spent for item in categories)
    remaining = max(0, assigned - spent)
    draw.text((7, 31), _money(snapshot, remaining), font=number, fill=black)
    draw.text((7, 59), "LEFT FROM THIS MONTH", font=micro, fill=black)
    _right(draw, f"{_money(snapshot, assigned)} ASSIGNED", 35, tiny, black)
    _right(draw, f"{_money(snapshot, spent)} SPENT", 52, micro, black)
    fraction = remaining / assigned if assigned else 0
    _bar(draw, black, 7, 78, 236, fraction)
    draw.text(
        (7, 101), f"{round(fraction * 100)}% REMAINS", font=tiny, fill=black
    )
    _right(draw, "ROLLOVER EXCLUDED", 103, micro, black)


def _draw_daily(draw, black, snapshot, now, fonts):
    _, number, tiny, micro = fonts
    _header(draw, black, snapshot, "DAILY ALLOWANCE", fonts)
    categories = snapshot.selected(
        _names("ynab_daily_categories", "Restaurants,Groceries")
    )
    assigned = sum(item.assigned for item in categories)
    spent = sum(item.spent for item in categories)
    remaining = max(0, assigned - spent)
    days = max(1, calendar.monthrange(now.year, now.month)[1] - now.day + 1)
    draw.text(
        (7, 31), _money(snapshot, remaining / days, 2), font=number, fill=black
    )
    draw.text((7, 59), "PER DAY", font=micro, fill=black)
    _right(draw, f"{_money(snapshot, remaining, 2)} LEFT", 35, tiny, black)
    _right(draw, f"{days} DAYS", 52, tiny, black)
    _bar(draw, black, 7, 78, 236, remaining / assigned if assigned else 0)
    draw.text(
        (7, 102),
        f"ASSIGNED {_money(snapshot, assigned)}",
        font=micro,
        fill=black,
    )
    _right(draw, f"SPENT {_money(snapshot, spent, 2)}", 102, micro, black)


def _rows(draw, black, rows, fonts, value_fn, fraction_fn):
    _, _, tiny, micro = fonts
    for index, item in enumerate(rows[:3]):
        y = 33 + index * 27
        name = item.name.upper()
        if draw.textbbox((0, 0), name, font=tiny)[2] > 76:
            while (
                name and draw.textbbox((0, 0), f"{name}…", font=tiny)[2] > 76
            ):
                name = name[:-1]
            name = f"{name.rstrip()}…"
        draw.text((7, y + 2), name, font=tiny, fill=black)
        _bar(draw, black, 88, y, 80, fraction_fn(item))
        _right(draw, value_fn(item), y + 1, tiny, black)
        if index < min(3, len(rows)) - 1:
            draw.line((7, y + 20, 243, y + 20), fill=black, width=1)


def _draw_active(draw, black, snapshot, fonts):
    _header(draw, black, snapshot, "ACTIVE ENVELOPES", fonts)
    categories = [
        item for item in _spending_categories(snapshot) if item.spent > 0
    ]
    categories.sort(
        key=lambda item: item.spent / item.assigned if item.assigned else 0,
        reverse=True,
    )
    _rows(
        draw,
        black,
        categories,
        fonts,
        lambda item: _money(snapshot, item.assigned_remaining, 2),
        lambda item: (
            item.assigned_remaining / item.assigned if item.assigned else 0
        ),
    )


def _draw_funding(draw, black, snapshot, fonts):
    _, _, tiny, micro = fonts
    _header(draw, black, snapshot, "THIS MONTH FUNDED", fonts)
    wanted = snapshot.selected(
        _names("ynab_funding_categories", "Vacation,Drier,New laptop")
    )
    wanted = [item for item in wanted if item.assigned > 0]
    for index, item in enumerate(wanted[:3]):
        y = 33 + index * 27
        draw.text((7, y + 2), item.name.upper()[:22], font=tiny, fill=black)
        _right(draw, _money(snapshot, item.assigned), y, tiny, black)
        if index < min(3, len(wanted)) - 1:
            draw.line((7, y + 20, 243, y + 20), fill=black, width=1)
    total = sum(item.assigned for item in wanted[:3])
    draw.text((7, 108), "CONTRIBUTIONS", font=micro, fill=black)
    _right(draw, f"TOTAL {_money(snapshot, total)}", 106, micro, black)


def _draw_exception(draw, black, white, snapshot, fonts):
    _, _, tiny, micro = fonts
    _header(draw, black, snapshot, "OUTSIDE MONTH PLAN", fonts)
    items = [
        item
        for item in snapshot.categories
        if item.assigned <= 0 and item.activity < 0
    ]
    items.sort(key=lambda item: item.activity)
    if not items:
        draw.text((7, 43), "ALL ACTIVITY", font=fonts[1], fill=black)
        draw.text((7, 75), "HAS A MONTHLY ENVELOPE", font=tiny, fill=black)
        return
    item = items[0]
    draw.rectangle((7, 33, 27, 53), fill=black)
    draw.text((13, 35), "!", font=tiny, fill=white)
    draw.text((36, 36), item.name.upper()[:25], font=fonts[0], fill=black)
    draw.text((7, 68), "ASSIGNED", font=micro, fill=black)
    _right(draw, _money(snapshot, item.assigned), 66, tiny, black)
    draw.text((7, 88), "ACTIVITY", font=micro, fill=black)
    _right(draw, _money(snapshot, item.spent, 2), 84, fonts[0], black)
    draw.rectangle((7, 103, 243, 115), outline=black, width=1)
    label = "REVIEW CATEGORY"
    width = draw.textbbox((0, 0), label, font=micro)[2]
    draw.text(((250 - width) // 2, 105), label, font=micro, fill=black)
