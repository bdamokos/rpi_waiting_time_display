from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_setup_and_startup_do_not_manage_linux_hardware_watchdog():
    paths = [
        ROOT / "setup_display.sh",
        ROOT / "docs/service/update_display.sh",
        ROOT / "docs/service/start_display.sh.example",
        ROOT / "docs/service/start_display.sh.remote_server.example",
        ROOT / "docs/service/start_display.sh.docker.example",
    ]
    banned = (
        "watchdog-device = /dev/watchdog",
        "max-load-1",
        "max-load-5",
        "systemctl enable watchdog",
        "systemctl start watchdog",
        "systemctl disable watchdog.service",
        "dtparam=watchdog=on",
    )
    for path in paths:
        source = path.read_text()
        for fragment in banned:
            assert fragment not in source, f"{fragment!r} remains in {path}"


def test_client_watchdog_has_no_whole_host_watchdog_or_power_action():
    paths = [
        ROOT / "display_watchdog.py",
        ROOT / "docs/service/display-watchdog.service",
        ROOT / "docs/service/display-client.service.example",
        ROOT / "docs/service/display-watchdog.config.json",
    ]
    banned = (
        "RuntimeWatchdogSec",
        "/dev/watchdog",
        "/sbin/reboot",
        "systemctl reboot",
        "systemctl poweroff",
        "shutdown -",
    )
    for path in paths:
        source = path.read_text()
        for fragment in banned:
            assert fragment not in source, f"{fragment!r} found in {path}"


def test_client_unit_bounds_systemd_watchdog_restarts():
    unit = (ROOT / "docs/service/display-client.service.example").read_text()
    assert "Type=notify" in unit
    assert "NotifyAccess=main" in unit
    assert "WatchdogSec=360" in unit
    assert "Restart=on-failure" in unit
    assert "StartLimitIntervalSec=6h" in unit
    assert "StartLimitBurst=3" in unit
