"""High-contrast breaking-news card for the 250x120 e-paper canvas."""

from PIL import Image, ImageDraw

from font_utils import get_font_paths
from rss_display import _ellipsize, _finish, _fonts
from text_layout import fit_wrapped_text


def draw_breaking_news(epd, entry, *, set_base_image=False):
    white = epd.WHITE if not epd.is_bw_display else 1
    black = epd.BLACK if not epd.is_bw_display else 0
    image = Image.new(
        "1" if epd.is_bw_display else "RGB", (epd.height, epd.width), white
    )
    draw = ImageDraw.Draw(image)
    header, title_font, _, tiny = _fonts()

    draw.rectangle((0, 0, 249, 25), fill=black)
    draw.text((7, 5), "BREAKING NEWS", font=header, fill=white)
    time_label = "NEW"
    if entry.published:
        time_label = entry.published.astimezone().strftime("%H:%M")
    time_width = draw.textbbox((0, 0), time_label, font=tiny)[2]
    draw.text((243 - time_width, 7), time_label, font=tiny, fill=white)
    source = _ellipsize(draw, entry.publication.upper(), tiny, 236)
    draw.text((7, 31), source, font=tiny, fill=black)
    draw.line((7, 44, 243, 44), fill=black, width=1)
    fitted = fit_wrapped_text(
        draw,
        entry.title,
        get_font_paths()["dejavu_bold"],
        min_size=14,
        max_size=24,
        max_width=236,
        max_height=66,
        max_lines=4,
    )
    for index, line in enumerate(fitted.lines):
        draw.text(
            (7, 50 + index * fitted.line_advance),
            line,
            font=fitted.font,
            fill=black,
        )
    _finish(epd, image, set_base_image)
