from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from vacation_privacy import DateWindow, VacationPrivacyMode


def test_disabled_policy_never_blocks():
    policy = VacationPrivacyMode(
        enabled=False,
        sensitive_displays=("calendar",),
        timezone="Europe/Brussels",
    )

    assert not policy.blocks(
        "calendar-agenda", datetime(2026, 8, 12, tzinfo=ZoneInfo("UTC"))
    )


def test_manual_mode_without_dates_is_always_active():
    policy = VacationPrivacyMode(
        enabled=True,
        sensitive_displays=("calendar", "token*"),
        timezone="Europe/Brussels",
    )

    now = datetime(2026, 8, 12, tzinfo=ZoneInfo("UTC"))
    assert policy.blocks("calendar-event", now)
    assert policy.blocks("token-always", now)
    assert not policy.blocks("weather", now)


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


def test_timezone_boundary_converts_aware_device_timestamp():
    policy = VacationPrivacyMode(
        enabled=True,
        sensitive_displays=("calendar",),
        windows=(DateWindow(date(2026, 8, 11), date(2026, 8, 11)),),
        timezone="Pacific/Kiritimati",
    )

    assert policy.blocks(
        "calendar-agenda",
        datetime(2026, 8, 10, 11, 30, tzinfo=ZoneInfo("America/Los_Angeles")),
    )


def test_naive_timestamp_is_rejected():
    policy = VacationPrivacyMode(
        enabled=True,
        windows=(DateWindow(date(2026, 8, 11), date(2026, 8, 11)),),
        timezone="UTC",
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        policy.is_active(datetime(2026, 8, 11))


def test_safe_fallback_returns_none_when_all_builtins_are_sensitive():
    policy = VacationPrivacyMode(
        enabled=True,
        sensitive_displays=("auto", "transit", "weather"),
        timezone="UTC",
    )

    assert policy.safe_fallback() is None
