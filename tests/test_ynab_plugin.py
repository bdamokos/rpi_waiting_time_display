import threading
from datetime import datetime, timedelta
from types import SimpleNamespace

from screen_arbiter import ScreenArbiter
from ynab_budget import YnabSnapshot
from ynab_plugin import YnabGlancePlugin


def _snapshot(*, stale=False, generated_at="2026-07-12T08:00:00+02:00"):
    return YnabSnapshot(
        generated_at=generated_at,
        month="2026-07-01",
        currency_symbol="€",
        categories=[],
        stale=stale,
    )


def _plugin(
    monkeypatch,
    rendered,
    *,
    enabled=True,
    base_mode_at=None,
    lock=None,
    on_release=None,
    is_current=None,
):
    monkeypatch.setenv("ynab_glance_enabled", "true" if enabled else "false")
    monkeypatch.setenv("ynab_glance_poll_seconds", "1")
    monkeypatch.setenv("ynab_glance_interval_seconds", "1800")
    monkeypatch.setenv("ynab_glance_duration_seconds", "60")
    monkeypatch.setenv("ynab_glance_offset_seconds", "900")
    monkeypatch.setenv("ynab_glance_priority", "20")
    monkeypatch.setattr(
        "ynab_plugin.draw_ynab_view",
        lambda epd, snapshot, view, **kwargs: rendered.append(
            (snapshot, view, kwargs)
        ),
    )
    client = SimpleNamespace(enabled=True, get_snapshot=lambda: _snapshot())
    return YnabGlancePlugin(
        object(),
        ScreenArbiter(),
        lock or threading.Lock(),
        client=client,
        views=["month", "daily", "active", "funding", "exception"],
        on_release=on_release,
        is_current=is_current,
        base_mode_at=base_mode_at or (lambda now: "transit"),
    )


def test_disabled_plugin_does_not_start_or_claim(monkeypatch):
    plugin = _plugin(monkeypatch, [], enabled=False)

    plugin.start()
    plugin.tick(datetime(2026, 7, 12, 8, 15), _snapshot())

    assert plugin._thread is None
    assert plugin.arbiter.active_owner() is None


def test_glance_claims_at_offset_and_releases_after_duration(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    start = datetime(2026, 7, 12, 8, 15)

    plugin.tick(start, _snapshot())

    claim = plugin.arbiter.claim_for(plugin.OWNER)
    assert claim.priority == 20
    assert claim.exclusive is False
    assert rendered[0][2]["set_base_image"] is True

    plugin.tick(start + timedelta(seconds=60), _snapshot())
    assert plugin.arbiter.active_owner() is None


def test_glance_is_offset_from_calendar_cadence(monkeypatch):
    plugin = _plugin(monkeypatch, [])

    assert not plugin._is_due(datetime(2026, 7, 12, 8, 0))
    assert plugin._is_due(datetime(2026, 7, 12, 8, 15))
    assert not plugin._is_due(datetime(2026, 7, 12, 8, 16))
    assert plugin._is_due(datetime(2026, 7, 12, 8, 45))


def test_successive_glances_advance_views_and_wrap(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    start = datetime(2026, 7, 12, 8, 15)

    for index in range(6):
        now = start + timedelta(minutes=30 * index)
        plugin.tick(now, _snapshot(generated_at=str(index)))
        plugin.tick(now + timedelta(seconds=60), _snapshot())

    views = [item[1] for item in rendered]
    view_indexes = [plugin.views.index(view) for view in views]
    assert all(
        current == (previous + 1) % len(plugin.views)
        for previous, current in zip(view_indexes, view_indexes[1:])
    )
    assert views[0] == views[-1]


def test_glance_does_not_redraw_unchanged_slot(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    start = datetime(2026, 7, 12, 8, 15)
    snapshot = _snapshot()

    plugin.tick(start, snapshot)
    plugin.tick(start + timedelta(seconds=10), snapshot)

    assert len(rendered) == 1


def test_glance_redraws_after_higher_priority_preemption(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    start = datetime(2026, 7, 12, 8, 15)
    snapshot = _snapshot()

    plugin.tick(start, snapshot)
    assert plugin.arbiter.claim("flight", 50, 30)
    plugin.tick(start + timedelta(seconds=10), snapshot)
    plugin.arbiter.release("flight")
    plugin.tick(start + timedelta(seconds=20), snapshot)

    assert len(rendered) == 2
    assert rendered[-1][2]["set_base_image"] is True


def test_glance_rechecks_ownership_after_acquiring_display_lock(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)

    class PreemptingLock:
        def __enter__(self):
            plugin.arbiter.claim("breaking-news", 70, 30)

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    plugin.display_lock = PreemptingLock()
    plugin.tick(datetime(2026, 7, 12, 8, 15), _snapshot())

    assert rendered == []


def test_stale_snapshot_renders_but_missing_snapshot_releases(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    start = datetime(2026, 7, 12, 8, 15)

    plugin.tick(start, _snapshot(stale=True))
    assert rendered[0][0].stale is True

    plugin.tick(start + timedelta(seconds=10), None)
    assert plugin.arbiter.active_owner() is None


def test_fixed_ynab_schedule_suppresses_glance(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered, base_mode_at=lambda now: "ynab")

    plugin.tick(datetime(2026, 7, 12, 8, 15), _snapshot())

    assert plugin.arbiter.active_owner() is None
    assert rendered == []


def test_stop_releases_active_claim(monkeypatch):
    plugin = _plugin(monkeypatch, [])
    plugin.tick(datetime(2026, 7, 12, 8, 15), _snapshot())

    plugin.stop()

    assert plugin.arbiter.active_owner() is None


def test_slot_identity_changes_across_dates(monkeypatch):
    plugin = _plugin(monkeypatch, [])
    first = datetime(2026, 7, 12, 8, 15)
    second = first + timedelta(days=1)

    assert plugin._slot_at(first) != plugin._slot_at(second)


def test_transient_preemption_redraws_when_pixels_are_no_longer_current(monkeypatch):
    rendered = []
    current_owner = [YnabGlancePlugin.OWNER]
    plugin = _plugin(
        monkeypatch,
        rendered,
        is_current=lambda: current_owner[0] == YnabGlancePlugin.OWNER,
    )
    start = datetime(2026, 7, 12, 8, 15)
    snapshot = _snapshot()

    plugin.tick(start, snapshot)
    current_owner[0] = "flight"
    plugin.tick(start + timedelta(seconds=10), snapshot)

    assert len(rendered) == 2
    assert rendered[-1][2]["set_base_image"] is True


def test_releasing_active_glance_requests_base_restoration(monkeypatch):
    restored = []
    plugin = _plugin(monkeypatch, [], on_release=lambda: restored.append(True))
    start = datetime(2026, 7, 12, 8, 15)

    plugin.tick(start, _snapshot())
    plugin.tick(start + timedelta(seconds=60), _snapshot())

    assert restored == [True]


def test_skipped_slot_does_not_consume_next_view(monkeypatch):
    rendered = []
    plugin = _plugin(monkeypatch, rendered)
    first = datetime(2026, 7, 12, 8, 15)
    skipped = first + timedelta(minutes=30)
    next_render = skipped + timedelta(minutes=30)

    plugin.tick(first, _snapshot())
    first_view = rendered[-1][1]
    plugin.tick(first + timedelta(seconds=60), _snapshot())
    plugin.tick(skipped, None)
    plugin.tick(next_render, _snapshot(generated_at="next"))

    assert plugin.views.index(rendered[-1][1]) == (
        plugin.views.index(first_view) + 1
    ) % len(plugin.views)
