import time

from basic import DisplayManager
from systemd_notify import SystemdNotifier


class FakeNotifier:
    enabled = True
    watchdog_interval = 360.0

    def __init__(self):
        self.ready_status = []
        self.watchdog_status = []

    def ready(self, status):
        self.ready_status.append(status)
        return True

    def watchdog(self, status):
        self.watchdog_status.append(status)
        return True


class Reporter:
    def __init__(self, last_success_at):
        self.last_success_at = last_success_at

    def snapshot(self):
        return {"sequence": 7, "last_success_at": self.last_success_at}


def test_notifier_respects_watchdog_pid_and_rate_limit():
    now = [20.0]
    notifier = SystemdNotifier(
        {
            "NOTIFY_SOCKET": "/run/example.sock",
            "WATCHDOG_USEC": "10000000",
            "WATCHDOG_PID": "123",
        },
        monotonic=lambda: now[0],
        pid=123,
    )
    messages = []
    notifier.notify = lambda *fields: messages.append(fields) or True

    assert notifier.ready("ready")
    assert notifier.watchdog("healthy")
    assert not notifier.watchdog("too soon")
    now[0] += 5
    assert notifier.watchdog("healthy again")
    assert messages[0] == ("READY=1", "STATUS=ready")
    assert messages[1][0] == "WATCHDOG=1"

    wrong_pid = SystemdNotifier(
        {
            "NOTIFY_SOCKET": "/run/example.sock",
            "WATCHDOG_USEC": "10000000",
            "WATCHDOG_PID": "999",
        },
        pid=123,
    )
    assert not wrong_pid.enabled


def test_display_manager_notifies_only_for_live_loop_and_fresh_success():
    manager = DisplayManager.__new__(DisplayManager)
    notifier = FakeNotifier()
    manager._systemd_notifier = notifier
    manager._watchdog_display_max_age = 300
    manager._control_loop_tick = time.monotonic()
    manager.epd = type("Display", (), {})()
    manager.epd._display_health_reporter = Reporter(time.time())

    assert manager.systemd_watchdog_tick()
    assert notifier.ready_status
    assert notifier.watchdog_status

    manager._control_loop_tick = time.monotonic() - 20
    assert not manager.systemd_watchdog_tick()

    manager._control_loop_tick = time.monotonic()
    manager.epd._display_health_reporter = Reporter(time.time() - 301)
    assert not manager.systemd_watchdog_tick()
