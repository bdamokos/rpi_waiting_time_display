import math
from datetime import datetime, timedelta, timezone

import pytest

import astronomy_utils


class FakeAngle:
    def __init__(self, degrees):
        self.degrees = degrees


class FakeTime:
    def __init__(self, value):
        self.value = value

    def utc_datetime(self):
        return self.value


class FakeTimescale:
    def now(self):
        return FakeTime(datetime(2023, 12, 23, 12, tzinfo=timezone.utc))

    def from_datetime(self, value):
        return FakeTime(value)


class FakeApparent:
    def __init__(self, body, time):
        self.body = body
        self.time = time

    @property
    def phase_angle(self):
        start = datetime(2023, 12, 23, 12, tzinfo=timezone.utc)
        elapsed_days = (self.time.value - start).total_seconds() / 86400
        return (135.0 + 12.2 * elapsed_days) % 360

    def apparent(self):
        return self

    def frame_latlon(self, _frame):
        angle = self.phase_angle if self.body == "moon" else 0.0
        return None, FakeAngle(angle), None

    def fraction_illuminated(self, _sun):
        return (1 - math.cos(math.radians(self.phase_angle))) / 2


class FakeObserver:
    def __init__(self, time):
        self.time = time

    def observe(self, body):
        return FakeApparent(body, self.time)


class FakeEarth:
    def at(self, time):
        return FakeObserver(time)


class FakeEphemeris(dict):
    def __init__(self):
        super().__init__(sun="sun", moon="moon", earth=FakeEarth())


class FakeLoad:
    def __init__(self):
        self.calls = []

    def timescale(self):
        return FakeTimescale()

    def __call__(self, filename):
        self.calls.append(filename)
        return FakeEphemeris()


@pytest.fixture(autouse=True)
def fake_ephemeris(monkeypatch):
    fake_load = FakeLoad()
    cached_get_moon_phase = astronomy_utils.get_moon_phase
    cached_get_moon_phase.cache_clear()
    monkeypatch.setattr(astronomy_utils, "load", fake_load)
    yield fake_load
    cached_get_moon_phase.cache_clear()


def test_get_moon_phase_structure():
    phase_data = astronomy_utils.get_moon_phase()

    assert set(phase_data) == {
        "phase_angle",
        "emoji",
        "name",
        "percent_illuminated",
    }
    assert isinstance(phase_data["phase_angle"], float)
    assert isinstance(phase_data["emoji"], str)
    assert isinstance(phase_data["name"], str)
    assert isinstance(phase_data["percent_illuminated"], float)
    assert 0 <= phase_data["phase_angle"] <= 360
    assert 0 <= phase_data["percent_illuminated"] <= 100


def test_get_moon_phase_specific_time():
    timestamp = datetime(2023, 12, 23, 12, tzinfo=timezone.utc)
    phase_data = astronomy_utils.get_moon_phase(timestamp)

    assert phase_data["phase_angle"] == pytest.approx(135.0)
    assert phase_data["name"] == "Waxing Gibbous"


def test_get_daily_moon_change(monkeypatch):
    phases = iter(
        [
            {"percent_illuminated": 40.0},
            {"percent_illuminated": 51.0},
        ]
    )
    monkeypatch.setattr(astronomy_utils, "get_moon_phase", lambda _time: next(phases))

    assert astronomy_utils.get_daily_moon_change() == {
        "current": 40.0,
        "tomorrow": 51.0,
        "change": 11.0,
    }


def test_get_upcoming_moon_phases(monkeypatch):
    phase_time = datetime(2023, 12, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(astronomy_utils.almanac, "moon_phases", lambda _eph: object())
    monkeypatch.setattr(
        astronomy_utils.almanac,
        "find_discrete",
        lambda _start, _end, _function: ([FakeTime(phase_time)], [0]),
    )

    assert astronomy_utils.get_upcoming_moon_phases(30) == [
        {"time": phase_time, "phase_name": "New Moon"}
    ]


def test_moon_phase_cache(fake_ephemeris):
    timestamp = datetime(2023, 12, 23, 12, tzinfo=timezone.utc)
    result1 = astronomy_utils.get_moon_phase(timestamp)
    result2 = astronomy_utils.get_moon_phase(timestamp)

    assert result1 is result2
    assert fake_ephemeris.calls == ["de421.bsp"]


def test_different_timestamps():
    timestamp1 = datetime(2023, 12, 23, 12, tzinfo=timezone.utc)
    timestamp2 = timestamp1 + timedelta(days=1)

    phase1 = astronomy_utils.get_moon_phase(timestamp1)
    phase2 = astronomy_utils.get_moon_phase(timestamp2)

    assert phase2["phase_angle"] - phase1["phase_angle"] == pytest.approx(12.2)
