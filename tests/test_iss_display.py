import pytest
from PIL import ImageOps

import iss
from display_adapter import MockDisplay
from font_utils import get_font_paths


@pytest.mark.parametrize("display_type", ["bw", "bwr"])
@pytest.mark.parametrize("rotation", [0, 90])
@pytest.mark.parametrize("emoji_font", ["absent", "text_fallback"])
def test_iss_satellite_renders_without_an_emoji_font(
    monkeypatch, tmp_path, display_type, rotation, emoji_font
):
    # Minimal render servers have text fonts but no satellite emoji glyph.
    fonts = {"dejavu_bold": get_font_paths()["dejavu_bold"]}
    if emoji_font == "text_fallback":
        fonts["emoji"] = fonts["dejavu_bold"]
    monkeypatch.setattr(iss, "get_font_paths", lambda: fonts)
    monkeypatch.setattr(iss, "display_rotation", rotation)
    monkeypatch.setenv("mock_display_type", display_type)
    monkeypatch.chdir(tmp_path)
    display = MockDisplay()
    frames = []
    monkeypatch.setattr(display, "getbuffer", lambda image: image)
    monkeypatch.setattr(display, "displayPartial", frames.append)

    iss.display_iss_info(
        display,
        {
            "latitude": 40.7,
            "longitude": 13.8,
            "altitude": 427.1,
            "distance": 1454.6,
            "azimuth": 143.6,
            "visible_until_human": "2026-10-15 10:58:16",
        },
    )

    assert len(frames) == 1
    frame = frames[0]
    assert frame.mode == ("1" if display_type == "bw" else "RGB")
    assert frame.size == ((250, 120) if rotation == 0 else (120, 250))
    landscape = frame.rotate(-rotation, expand=True).convert("L")
    satellite = ImageOps.invert(landscape.crop((5, 32, 61, 88)))
    bounds = satellite.getbbox()
    assert bounds is not None
    assert bounds[2] - bounds[0] >= 40
    assert bounds[3] - bounds[1] >= 40
    assert sum(satellite.histogram()[129:]) >= 250
    assert ImageOps.invert(landscape.crop((70, 5, 250, 105))).getbbox()
