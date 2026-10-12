import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "latitude,longitude,expected",
    [
        ("", "4.3517", [50.8503, 4.3517]),
        ("50.8503", "not-a-coordinate", [50.8503, 4.3517]),
        ("47.5", "19.04", [47.5, 19.04]),
    ],
)
def test_display_manager_uses_validated_startup_coordinates(
    tmp_path, latitude, longitude, expected
):
    # Exercise import-time validation and real manager construction together.
    environment = dict(os.environ)
    environment.update(
        {
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "Coordinates_LAT": latitude,
            "Coordinates_LNG": longitude,
            "display_file_logging": "false",
            "weather_enabled": "false",
            "transit_enabled": "false",
            "flights_enabled": "false",
            "iss_enabled": "false",
            "aeroapi_enabled": "false",
            "ynab_enabled": "false",
            "calendar_enabled": "false",
            "rss_watch_enabled": "false",
            "breaking_news_enabled": "false",
            "home_assistant_enabled": "false",
            "token_usage_enabled": "false",
            "display_override_enabled": "false",
            "flight_statistics_db": str(tmp_path / "statistics.sqlite3"),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from basic import DisplayManager; "
            "from display_adapter import MockDisplay; "
            "manager = DisplayManager(MockDisplay()); "
            "print(json.dumps([manager.coordinates_lat, manager.coordinates_lng])); "
            "manager.cleanup()",
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected
