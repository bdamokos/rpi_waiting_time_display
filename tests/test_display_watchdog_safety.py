import subprocess
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
        source = path.read_text(encoding="utf-8")
        for fragment in banned:
            assert fragment not in source, f"{fragment!r} remains in {path}"


def test_client_watchdog_has_no_whole_host_watchdog_or_power_action():
    paths = [
        ROOT / "display_watchdog.py",
        ROOT / "docs/service/display-watchdog.service",
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
        source = path.read_text(encoding="utf-8")
        for fragment in banned:
            assert fragment not in source, f"{fragment!r} found in {path}"


def test_secondary_auditor_never_sends_systemd_notify_keepalives():
    source = (ROOT / "display_watchdog.py").read_text(encoding="utf-8")
    assert "WATCHDOG=1" not in source
    assert "READY=1" not in source


def test_installers_reject_missing_service_argument_cleanly():
    for name in ("setup_display_watchdog.sh", "uninstall_display_watchdog.sh"):
        completed = subprocess.run(
            ["sh", str(ROOT / "docs/service" / name), "--service"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 2
        assert "shift" not in completed.stderr.lower()


def test_split_client_install_does_not_add_a_service_drop_in():
    source = (ROOT / "docs/service/setup_display_watchdog.sh").read_text(
        encoding="utf-8"
    )
    assert 'if [ "$SERVICE_NAME" != display-client.service ]; then' in source
    assert source.index('if [ "$SERVICE_NAME" != display-client.service ]; then') < (
        source.index('install -m 0644 "$SCRIPT_DIR/display-watchdog-health.conf"')
    )
