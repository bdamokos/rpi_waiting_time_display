from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_UNIT = ROOT / "docs" / "service" / "display-client.service.example"


def _unit_settings():
    settings = {}
    section = None
    for raw_line in CLIENT_UNIT.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        key, value = line.split("=", 1)
        settings[(section, key)] = value
    return settings


def test_client_unit_main_loop_owns_notify_watchdog():
    settings = _unit_settings()

    assert settings[("Service", "Type")] == "notify"
    assert settings[("Service", "NotifyAccess")] == "main"
    assert settings[("Service", "WatchdogSec")] == "45"
    assert settings[("Service", "Restart")] == "on-failure"


def test_client_unit_has_conservative_long_window_restart_budget():
    settings = _unit_settings()

    assert settings[("Unit", "StartLimitIntervalSec")] == "6h"
    assert settings[("Unit", "StartLimitBurst")] == "3"
    assert settings[("Unit", "StartLimitAction")] == "none"
