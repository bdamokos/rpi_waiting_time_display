import json
import subprocess

from display_watchdog import (
    DEFAULT_CONFIG,
    assess,
    collect_client_health,
    exact_physical_target_matches,
    restart_client_service,
    server_health_from_client,
    validate_config,
)

NOW = 10_000.0


def config(**updates):
    value = dict(DEFAULT_CONFIG)
    value["physical_target"] = dict(DEFAULT_CONFIG["physical_target"])
    value.update(updates)
    return value


def service(**updates):
    value = {
        "reachable": True,
        "Type": "notify",
        "NotifyAccess": "main",
        "WatchdogUSec": 360_000_000,
        "ActiveState": "active",
        "SubState": "running",
        "MainPID": 42,
        "NRestarts": 0,
        "service_age_seconds": 600,
    }
    value.update(updates)
    return value


def host(**updates):
    value = {
        "distress": False,
        "distress_reasons": [],
        "d_state_processes": 0,
        "swap_used_ratio": 0.2,
        "swapout_pages_per_second": 0.0,
        "iowait_ratio": 0.0,
    }
    value.update(updates)
    return value


def client(**updates):
    value = {"fresh": True, "display_success_fresh": True, "sequence": 3}
    value.update(updates)
    return value


def server(**updates):
    value = {"configured": False, "reachable": None, "fresh": None}
    value.update(updates)
    return value


def runtime():
    return {"last_main_pid": 42, "main_pid_changed_at": NOW - 600}


def evaluate(
    cfg=None,
    service_value=None,
    host_value=None,
    client_value=None,
    server_value=None,
    runtime_value=None,
    persistent=None,
):
    return assess(
        cfg or config(),
        NOW,
        service_value or service(),
        host_value or host(),
        client_value or client(),
        server_value or server(),
        runtime_value or runtime(),
        persistent or {},
        "boot",
    )


def test_healthy_notify_client_uses_systemd_as_primary():
    result = evaluate()
    assert result["classification"] == "healthy"
    assert result["systemd_watchdog_primary"]
    assert not result["fallback_recovery_requested"]


def test_host_distress_inhibits_recovery_and_escalates():
    result = evaluate(
        cfg=config(recovery_enabled=True, consecutive_failures=1),
        host_value=host(distress=True, distress_reasons=["d_state_processes"]),
        client_value=client(fresh=False),
    )
    assert result["classification"] == "host_kernel_storage_distress"
    assert result["human_escalation"]
    assert not result["fallback_recovery_requested"]


def test_server_failure_is_not_misclassified_as_client_failure():
    result = evaluate(
        cfg=config(recovery_enabled=True, consecutive_failures=1),
        client_value=client(fresh=False),
        server_value=server(configured=True, reachable=False, fresh=False),
    )
    assert result["classification"] == "server_network_distress"
    assert not result["fallback_recovery_requested"]


def test_notify_guarded_stale_client_does_not_race_systemd():
    result = evaluate(
        cfg=config(recovery_enabled=True, consecutive_failures=1),
        client_value=client(fresh=False),
    )
    assert result["classification"] == "client_unhealthy_systemd_guarded"
    assert not result["fallback_recovery_requested"]


def test_notify_client_heartbeat_must_match_main_pid_and_boot():
    result = evaluate(
        client_value=client(
            available=True,
            fresh=True,
            pid=999,
            boot_id="wrong-boot",
        )
    )
    assert result["classification"] == "client_unhealthy_systemd_guarded"
    assert not result["client"]["identity_matches"]


def test_legacy_render_failure_requires_consecutive_failures():
    cfg = config(recovery_enabled=True, consecutive_failures=3)
    legacy = service(Type="simple", NotifyAccess="none", WatchdogUSec=0)
    observed = runtime()
    for expected in (1, 2):
        result = evaluate(
            cfg=cfg,
            service_value=legacy,
            client_value=client(fresh=False),
            runtime_value=observed,
        )
        assert result["consecutive_failures"] == expected
        assert not result["fallback_recovery_requested"]
    result = evaluate(
        cfg=cfg,
        service_value=legacy,
        client_value=client(fresh=False),
        runtime_value=observed,
    )
    assert result["fallback_recovery_requested"]


def test_startup_grace_blocks_failure_counting():
    observed = runtime()
    observed["main_pid_changed_at"] = NOW
    result = evaluate(
        cfg=config(recovery_enabled=True, consecutive_failures=1),
        service_value=service(service_age_seconds=5),
        client_value=client(fresh=False),
        runtime_value=observed,
    )
    assert result["classification"] == "startup_grace"
    assert result["consecutive_failures"] == 0


def test_persistent_budget_and_cooldown_block_fallback():
    result = evaluate(
        cfg=config(recovery_enabled=True, consecutive_failures=1),
        service_value=service(
            ActiveState="failed",
            SubState="failed",
            MainPID=0,
            Type="simple",
            WatchdogUSec=0,
        ),
        persistent={
            "restart_timestamps": [NOW - 10],
            "boot_id": "boot",
            "boot_restart_count": 1,
        },
    )
    assert result["classification"] == "service_failure"
    assert result["budget"]["cooldown_remaining_seconds"] > 0
    assert result["human_escalation"]
    assert not result["fallback_recovery_requested"]


def test_client_health_uses_sequence_and_tmpfs_json(tmp_path):
    health_path = tmp_path / "health.json"
    health_path.write_text(
        json.dumps({"schema_version": 1, "last_success_at": NOW - 5, "sequence": 9})
    )
    cfg = config(client_health_path=str(health_path))
    observed = {"last_sequence": 8}
    result = collect_client_health(cfg, NOW, observed)
    assert result["fresh"]
    assert result["sequence_advanced"]
    assert observed["last_sequence"] == 9


def test_embedded_server_freshness_is_independent_from_client_freshness():
    fresh = server_health_from_client(
        config(),
        NOW,
        {
            "server_generated_at": NOW - 5,
            "server_received_at": NOW - 4,
        },
    )
    assert fresh["configured"]
    assert fresh["fresh"]
    assert fresh["source"] == "client_health"

    stale = server_health_from_client(
        config(server_max_age_seconds=30),
        NOW,
        {
            "server_generated_at": NOW - 31,
            "server_received_at": NOW - 30,
        },
    )
    assert not stale["fresh"]


def test_restart_command_is_client_service_only():
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    succeeded, _ = restart_client_service(
        config(service_name="display-client.service"), runner
    )
    assert succeeded
    assert calls == [
        ["/bin/systemctl", "restart", "--no-block", "display-client.service"]
    ]


def test_reboot_recommendation_identity_requires_three_exact_proofs():
    actual = {
        "hostname": "display-pi",
        "machine_id_sha256": "abc",
        "hardware_model": "Raspberry Pi Zero 2 W Rev 1.0",
        "device_tree_serial_sha256": "serial",
    }
    assert not exact_physical_target_matches({}, actual)
    assert exact_physical_target_matches(dict(actual), actual)
    mismatch = dict(actual)
    mismatch["hostname"] = "other"
    assert not exact_physical_target_matches(mismatch, actual)


def test_runtime_outputs_must_stay_in_run():
    bad = config(metrics_path="/var/lib/display-watchdog/metrics.prom")
    try:
        validate_config(bad)
    except ValueError as error:
        assert "must be under /run" in str(error)
    else:
        raise AssertionError("persistent metrics path was accepted")
