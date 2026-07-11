"""High-contrast breaking-news card for the 250x120 e-paper canvas."""

from PIL import Image, ImageDraw

from rss_display import _ellipsize, _finish, _fonts, _wrap


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
    for index, line in enumerate(_wrap(draw, entry.title, title_font, 236, 4)):
        draw.text((7, 50 + index * 17), line, font=title_font, fill=black)
    _finish(epd, image, set_base_image)
