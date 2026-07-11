from PIL import Image, ImageChops, ImageDraw

from display_adapter import MockDisplay
from tests.test_token_usage import SAMPLE
from token_display import (
    _cumulative_points,
    _fonts,
    _reset_badge,
    _today_cost,
    draw_month_usage,
    draw_usage_limits,
    draw_usage_reset,
)
from token_usage import TokenUsageSnapshot


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


def test_reset_notice_renders_as_a_distinct_screen(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    display = MockDisplay()
    snapshot = TokenUsageSnapshot.from_dict(SAMPLE)

    draw_usage_limits(display, snapshot, set_base_image=True)
    limits = Image.open("debug_output.png").copy()

    snapshot.reset_notice = "primary"
    draw_usage_reset(display, snapshot, set_base_image=True)
    reset = Image.open("debug_output.png").copy()

    assert reset.size == (display.height, display.width)
    assert ImageChops.difference(limits, reset).getbbox() is not None


def test_reset_badge_is_clipped_into_top_right_corner():
    image = Image.new("1", (250, 122), 1)
    _reset_badge(ImageDraw.Draw(image), 0, 1, 1, _fonts()[3])

    assert image.getpixel((249, 1)) == 0
    assert image.getpixel((226, 1)) == 1


def test_month_view_cumulative_line_runs_from_chart_origin_to_top_right():
    snapshot = TokenUsageSnapshot.from_dict(SAMPLE)

    points = _cumulative_points(snapshot.daily, 7, 73, 243, 109)

    assert points[0] == (7, 109)
    assert points[-1] == (243, 73)
    assert all(
        current[1] <= previous[1] for previous, current in zip(points, points[1:])
    )


def test_month_view_uses_snapshot_date_for_today_total():
    snapshot = TokenUsageSnapshot.from_dict(SAMPLE)

    assert _today_cost(snapshot) == 83.5
