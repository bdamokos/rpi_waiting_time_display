from PIL import Image

from display_adapter import MockDisplay
from token_display import draw_month_usage, draw_usage_limits
from token_usage import TokenUsageSnapshot

from tests.test_token_usage import SAMPLE


def test_token_views_render_at_display_dimensions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    display = MockDisplay()
    snapshot = TokenUsageSnapshot.from_dict(SAMPLE)

    draw_month_usage(display, snapshot, set_base_image=True)
    month = Image.open("debug_output.png")
    assert month.size == (display.height, display.width)

    draw_usage_limits(display, snapshot, set_base_image=True)
    limits = Image.open("debug_output.png")
    assert limits.size == (display.height, display.width)
