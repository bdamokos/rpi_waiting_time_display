from datetime import date, datetime
from zoneinfo import ZoneInfo

from vacation_privacy import DateWindow, VacationPrivacyMode


def test_disabled_policy_never_blocks():
    policy = VacationPrivacyMode(
        enabled=False,
        sensitive_displays=("calendar",),
        timezone="Europe/Brussels",
    )

    assert not policy.blocks("calendar-agenda", datetime(2026, 8, 12))


def test_manual_mode_without_dates_is_always_active():
    policy = VacationPrivacyMode(
        enabled=True,
        sensitive_displays=("calendar", "token*"),
        timezone="Europe/Brussels",
    )

    assert policy.blocks("calendar-event", datetime(2026, 8, 12))
    assert policy.blocks("token-always", datetime(2026, 8, 12))
    assert not policy.blocks("weather", datetime(2026, 8, 12))


def test_date_windows_are_inclusive_in_configured_timezone():
    policy = VacationPrivacyMode(
        enabled=True,
        sensitive_displays=("ynab",),
        windows=(DateWindow(date(2026, 8, 11), date(2026, 8, 14)),),
        timezone="Europe/Brussels",
    )

    assert policy.blocks(
        "ynab-glance",
        datetime(2026, 8, 10, 22, 30, tzinfo=ZoneInfo("UTC")),
    )
    assert not policy.blocks(
        "ynab-glance",
        datetime(2026, 8, 14, 22, 30, tzinfo=ZoneInfo("UTC")),
    )


def test_invalid_environment_fails_closed(monkeypatch):
    monkeypatch.setenv("vacation_mode_enabled", "true")
    monkeypatch.setenv("vacation_mode_sensitive_displays", "calendar,ynab,token")
    monkeypatch.setenv("vacation_mode_blackout_dates", "not-a-date")

    policy = VacationPrivacyMode.from_env()

    assert policy.fail_closed
    assert policy.blocks("calendar-agenda")


def test_safe_fallback_skips_sensitive_configured_mode():
    policy = VacationPrivacyMode(
        enabled=True,
        sensitive_displays=("transit",),
        timezone="UTC",
        fallback_mode="transit",
    )

    assert policy.safe_fallback() == "weather"
