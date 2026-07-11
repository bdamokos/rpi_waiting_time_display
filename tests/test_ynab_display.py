from datetime import datetime

from PIL import Image

from display_adapter import MockDisplay
from ynab_budget import YnabSnapshot
from ynab_display import draw_ynab_view

SAMPLE = {
    "generated_at": "2026-07-11T10:42:00+02:00",
    "month": "2026-07-01",
    "currency_symbol": "€",
    "categories": [
        {
            "name": "Dining",
            "group": "Food",
            "assigned": 400,
            "activity": -82.43,
            "available": 317.57,
        },
        {
            "name": "Groceries",
            "group": "Food",
            "assigned": 400,
            "activity": -18.24,
            "available": 381.76,
        },
        {
            "name": "Gadgets",
            "group": "Fun",
            "assigned": 150,
            "activity": -92.51,
            "available": 138.57,
        },
        {
            "name": "Holiday",
            "group": "Savings Goals",
            "assigned": 500,
            "activity": 0,
            "available": 2500,
        },
        {
            "name": "Uncategorized",
            "group": "Internal",
            "assigned": 0,
            "activity": -85.51,
            "available": -85.51,
        },
    ],
}


def test_all_ynab_views_render_at_native_dimensions(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ynab_daily_categories", "Dining,Groceries")
    monkeypatch.setenv("ynab_funding_categories", "Holiday")
    monkeypatch.setenv("mock_display_type", "bw")
    display = MockDisplay()
    snapshot = YnabSnapshot.from_dict(SAMPLE)
    for view in ("month", "daily", "active", "funding", "exception"):
        draw_ynab_view(
            display,
            snapshot,
            view,
            now=datetime(2026, 7, 11),
            set_base_image=True,
        )
        image = Image.open("debug_output.png")
        assert image.size == (display.height, display.width)
        assert image.mode == "1"
        assert image.getbbox() is not None
