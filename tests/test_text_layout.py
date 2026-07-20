from PIL import Image, ImageDraw

from font_utils import get_font_paths
from text_layout import fit_wrapped_text


def _draw():
    return ImageDraw.Draw(Image.new("1", (250, 120), 1))


def test_short_text_grows_to_maximum_size():
    fitted = fit_wrapped_text(
        _draw(),
        "Short update",
        get_font_paths()["dejavu_bold"],
        min_size=11,
        max_size=24,
        max_width=236,
        max_height=70,
        max_lines=4,
    )

    assert fitted.size == 24
    assert fitted.lines == ("Short update",)
    assert fitted.height > 0
    assert not fitted.truncated


def test_longer_text_uses_largest_size_that_fits_without_truncation():
    fitted = fit_wrapped_text(
        _draw(),
        "A longer update that needs several lines but still fits in its content area",
        get_font_paths()["dejavu"],
        min_size=11,
        max_size=24,
        max_width=180,
        max_height=60,
        max_lines=4,
    )

    assert 11 <= fitted.size < 24
    assert " ".join(fitted.lines) == (
        "A longer update that needs several lines but still fits in its content area"
    )
    assert not fitted.truncated


def test_overflow_at_minimum_size_is_ellipsized():
    fitted = fit_wrapped_text(
        _draw(),
        "This text is deliberately much too long for one very narrow line",
        get_font_paths()["dejavu"],
        min_size=11,
        max_size=18,
        max_width=80,
        max_height=15,
        max_lines=1,
    )

    assert fitted.size == 11
    assert fitted.truncated
    assert fitted.lines[-1].endswith("…")
