import threading
from datetime import datetime

from basic import DisplayManager
from screen_arbiter import ScreenArbiter
from vacation_privacy import VacationPrivacyMode


class FixedSchedule:
    def __init__(self, mode):
        self.mode = mode

    def mode_at(self, _now):
        return self.mode


def _active_policy(*names):
    return VacationPrivacyMode(
        enabled=True,
        sensitive_displays=names,
        timezone="Europe/Brussels",
        fallback_mode="transit",
    )


def test_sensitive_scheduled_mode_uses_safe_fallback():
    manager = DisplayManager.__new__(DisplayManager)
    manager.display_schedule = FixedSchedule("token-always")
    manager.vacation_privacy = _active_policy("token")

    assert manager._scheduled_mode(datetime(2026, 8, 12)) == "transit"


def test_sensitive_override_is_rejected_before_claiming_screen():
    manager = DisplayManager.__new__(DisplayManager)
    manager.screen_arbiter = ScreenArbiter()
    manager.vacation_privacy = _active_policy("calendar")

    result = manager.request_display_override("calendar")

    assert not result["accepted"]
    assert result["error"] == "module hidden by vacation privacy mode"
    assert manager.screen_arbiter.active_owner() is None


def test_active_sensitive_override_is_released_at_blackout_boundary():
    manager = DisplayManager.__new__(DisplayManager)
    manager.screen_arbiter = ScreenArbiter()
    manager.vacation_privacy = _active_policy("calendar")
    manager._override_lock = threading.RLock()
    manager._override_module = "calendar"
    manager._override_generation = 1
    manager._last_screen_owner = manager.OVERRIDE_SCREEN_OWNER
    manager.current_display_mode = "calendar-agenda"
    manager.screen_arbiter.claim(manager.OVERRIDE_SCREEN_OWNER, 30, 300)

    assert manager._enforce_vacation_privacy(datetime(2026, 8, 12))
    assert manager._override_module is None
    assert manager.screen_arbiter.active_owner() is None
