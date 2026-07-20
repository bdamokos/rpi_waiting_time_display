"""Reusable text fitting helpers for bounded e-paper content areas."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from PIL import ImageDraw, ImageFont


@dataclass(frozen=True)
class FittedText:
    """A font and wrapped lines selected to fit a rectangular content area."""

    font: ImageFont.ImageFont
    lines: tuple[str, ...]
    line_advance: int
    size: int
    truncated: bool = False


@lru_cache(maxsize=128)
def _truetype(font_path: str, size: int):
    return ImageFont.truetype(font_path, size)


def _normalize(text: str) -> str:
    return " ".join(str(text).split())


def _ellipsize(draw, text: str, font, max_width: int) -> str:
    text = _normalize(text)
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    suffix = "…"
    while text and draw.textbbox((0, 0), text + suffix, font=font)[2] > max_width:
        text = text[:-1]
    return text.rstrip() + suffix if text else suffix


def _wrap_all(draw, text: str, font, max_width: int) -> list[str]:
    words = _normalize(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _line_metrics(draw, font, spacing: int) -> tuple[int, int]:
    bounds = draw.textbbox((0, 0), "Ag", font=font)
    line_bottom = max(1, bounds[3])
    line_advance = max(1, bounds[3] - bounds[1] + spacing)
    return line_advance, line_bottom


def _fits(draw, lines, font, max_width, max_height, max_lines, spacing):
    if not lines:
        return True, 1
    if max_lines is not None and len(lines) > max_lines:
        return False, 1
    if any(draw.textbbox((0, 0), line, font=font)[2] > max_width for line in lines):
        return False, 1
    advance, bottom = _line_metrics(draw, font, spacing)
    height = (len(lines) - 1) * advance + bottom
    return height <= max_height, advance


def fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_path: str,
    *,
    min_size: int,
    max_size: int,
    max_width: int,
    max_height: int,
    max_lines: int | None = None,
    spacing: int = 2,
) -> FittedText:
    """Choose the largest font that contains all text inside the given bounds.

    Font sizes are tried progressively from ``min_size`` through ``max_size``.
    If the text cannot fit even at the minimum, the minimum-size result is
    clipped to the available line count and ellipsized.
    """

    if min_size <= 0 or max_size < min_size:
        raise ValueError("font sizes must satisfy 0 < min_size <= max_size")
    if max_width <= 0 or max_height <= 0:
        raise ValueError("text bounds must be positive")
    if max_lines is not None and max_lines <= 0:
        raise ValueError("max_lines must be positive")

    def minimum_result(font) -> FittedText:
        lines = _wrap_all(draw, text, font, max_width) or [""]
        advance, bottom = _line_metrics(draw, font, spacing)
        height_lines = max(1, 1 + max(0, max_height - bottom) // advance)
        line_limit = (
            min(height_lines, max_lines) if max_lines is not None else height_lines
        )
        truncated = len(lines) > line_limit or any(
            draw.textbbox((0, 0), line, font=font)[2] > max_width for line in lines
        )
        visible = lines[:line_limit]
        if truncated:
            remainder = " ".join(lines[line_limit - 1:])
            visible[-1] = _ellipsize(draw, remainder, font, max_width)
        return FittedText(font, tuple(visible), advance, min_size, truncated)

    best = None
    for size in range(min_size, max_size + 1):
        try:
            font = _truetype(font_path, size)
        except OSError:
            # A bitmap fallback cannot be progressively resized. Return it as
            # the minimum-size layout instead of pretending it reached max_size.
            return minimum_result(ImageFont.load_default())
        lines = _wrap_all(draw, text, font, max_width)
        fits, advance = _fits(
            draw, lines, font, max_width, max_height, max_lines, spacing
        )
        if not fits:
            # Larger fonts cannot recover width, height, or line-count space.
            break
        best = FittedText(font, tuple(lines), advance, size)
        if not hasattr(font, "size"):
            break

    if best is not None:
        return best

    try:
        font = _truetype(font_path, min_size)
    except OSError:
        font = ImageFont.load_default()
    return minimum_result(font)
