import pytest

from screen_arbiter import ScreenArbiter


class FakeClock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_base_display_is_active_without_claims():
    arbiter = ScreenArbiter()

    assert arbiter.active_owner() is None
    assert arbiter.can_render()
    assert not arbiter.can_render("flight")


def test_higher_priority_claim_preempts_and_release_restores_previous_owner():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)

    assert arbiter.claim("calendar-upcoming", 30, 300)
    assert arbiter.claim("flight", 50, 30)
    assert arbiter.active_owner() == "flight"

    assert arbiter.release("flight")
    assert arbiter.active_owner() == "calendar-upcoming"


def test_expiry_returns_control_to_base():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)
    arbiter.claim("flight", 50, 30)

    clock.advance(30)

    assert arbiter.active_owner() is None
    assert arbiter.can_render()
    assert not arbiter.has_claim("flight")


def test_exclusive_winner_cannot_be_preempted_but_must_expire():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)
    arbiter.claim("calendar-exclusive", 70, 600, exclusive=True)

    assert not arbiter.claim("emergency", 100, 60)
    assert arbiter.active_owner() == "calendar-exclusive"

    clock.advance(600)

    assert arbiter.active_owner() is None


def test_exclusive_claim_waits_for_a_higher_priority_current_owner():
    arbiter = ScreenArbiter()
    arbiter.claim("flight", 50, 30)

    assert not arbiter.claim("low-exclusive", 20, 60, exclusive=True)
    assert arbiter.active_owner() == "flight"

    arbiter.release("flight")
    assert arbiter.active_owner() == "low-exclusive"


def test_equal_priority_keeps_current_owner_until_release():
    arbiter = ScreenArbiter()
    arbiter.claim("first", 50, 30)
    arbiter.claim("second", 50, 30)

    assert arbiter.active_owner() == "first"
    arbiter.release("first")
    assert arbiter.active_owner() == "second"


def test_refreshing_claim_extends_expiry_without_changing_tie_order():
    clock = FakeClock()
    arbiter = ScreenArbiter(clock)
    arbiter.claim("first", 50, 10)
    arbiter.claim("second", 50, 30)
    clock.advance(5)

    arbiter.claim("first", 50, 20)
    clock.advance(10)

    assert arbiter.active_owner() == "first"


@pytest.mark.parametrize("owner", ["", "   "])
def test_claim_rejects_empty_owner(owner):
    with pytest.raises(ValueError):
        ScreenArbiter().claim(owner, 1, 1)


def test_claim_rejects_non_positive_ttl():
    with pytest.raises(ValueError):
        ScreenArbiter().claim("flight", 1, 0)
