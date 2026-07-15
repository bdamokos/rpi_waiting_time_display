#!/usr/bin/env python3
"""Bounded display-client health auditor and migration recovery fallback.

The primary hang detector for the split client is systemd's notify watchdog.
This oneshot auditor classifies host, server/network, service, and render health;
exports tmpfs metrics; and provides a budgeted client-service-only fallback for
the legacy monolith.  It contains no reboot, shutdown, or power-control action.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

SCHEMA_VERSION = 1
SPLIT_CLIENT_SERVICE = "display-client.service"
SERVICE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.@:-]+\.service$")
DEFAULT_CONFIG: dict[str, Any] = {
    "service_name": "display-client.service",
    "systemctl_path": "/bin/systemctl",
    "client_health_path": "/run/rpi-waiting-time-display/client-health.json",
    "legacy_debug_png_enabled": False,
    "debug_png_path": "/run/rpi-waiting-time-display/debug_output.png",
    "server_health_path": "",
    "server_health_url": "",
    "server_timeout_seconds": 3,
    "server_timestamp_fields": [
        "generated_at",
        "published_at",
        "server_generated_at",
        "updated_at",
        "last_success_at",
        "timestamp",
    ],
    "startup_grace_seconds": 300,
    "client_max_age_seconds": 300,
    "debug_png_max_age_seconds": 300,
    "server_max_age_seconds": 300,
    "consecutive_failures": 3,
    "recovery_enabled": False,
    "cooldown_seconds": 900,
    "cycle_window_seconds": 21600,
    "max_restarts_per_window": 2,
    "max_restarts_per_boot": 3,
    "max_d_state_processes": 0,
    "min_available_memory_mb": 96,
    "high_swap_used_ratio": 0.9,
    "max_swapout_pages_per_second": 64,
    "max_iowait_ratio": 0.35,
    "runtime_state_path": "/run/display-watchdog/observations.json",
    "persistent_state_path": "/var/lib/display-watchdog/recovery-state.json",
    "metrics_path": "/run/display-watchdog/metrics.prom",
    "status_path": "/run/display-watchdog/status.json",
    "human_reboot_recommendation_enabled": False,
    "physical_target": {
        "hostname": "",
        "machine_id_sha256": "",
        "hardware_model": "",
        "device_tree_serial_sha256": "",
    },
}


def _atomic_write(path: Path, content: str, mode: Optional[int] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(path.parent)
    )
    try:
        if mode is not None:
            os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _write_json(path: str, payload: dict[str, Any], mode: Optional[int] = None) -> None:
    _atomic_write(
        Path(path),
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        mode,
    )


def _read_json(path: str, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else dict(default)
    except (OSError, ValueError):
        return dict(default)


def load_config(path: str) -> dict[str, Any]:
    supplied = _read_json(path, {})
    config = dict(DEFAULT_CONFIG)
    config.update(supplied)
    timestamp_fields = supplied.get(
        "server_timestamp_fields", DEFAULT_CONFIG["server_timestamp_fields"]
    )
    config["server_timestamp_fields"] = (
        list(timestamp_fields)
        if isinstance(timestamp_fields, list)
        else timestamp_fields
    )
    target = dict(DEFAULT_CONFIG["physical_target"])
    target.update(supplied.get("physical_target", {}))
    config["physical_target"] = target
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    service = str(config["service_name"])
    if not SERVICE_NAME_PATTERN.fullmatch(service):
        raise ValueError(f"unsafe service_name: {service!r}")
    positive = (
        "startup_grace_seconds",
        "client_max_age_seconds",
        "debug_png_max_age_seconds",
        "server_max_age_seconds",
        "consecutive_failures",
        "cooldown_seconds",
        "cycle_window_seconds",
        "max_restarts_per_window",
        "max_restarts_per_boot",
    )
    for key in positive:
        if float(config[key]) <= 0:
            raise ValueError(f"{key} must be positive")
    for key in ("runtime_state_path", "metrics_path", "status_path"):
        path = os.path.abspath(str(config[key]))
        if os.path.commonpath((path, "/run")) != "/run":
            raise ValueError(f"{key} must be under /run")
    for key in ("client_health_path", "server_health_path"):
        configured_path = str(config.get(key, "")).strip()
        if not configured_path:
            continue
        path = os.path.abspath(configured_path)
        if os.path.commonpath((path, "/run")) != "/run":
            raise ValueError(f"{key} must be under /run")
    persistent_path = os.path.abspath(str(config["persistent_state_path"]))
    if os.path.commonpath((persistent_path, "/var/lib/display-watchdog")) != (
        "/var/lib/display-watchdog"
    ):
        raise ValueError(
            "persistent_state_path must be under /var/lib/display-watchdog"
        )
    systemctl_path = os.path.abspath(str(config["systemctl_path"]))
    if systemctl_path not in {"/bin/systemctl", "/usr/bin/systemctl"}:
        raise ValueError("systemctl_path must name the system systemctl binary")
    server_url = str(config.get("server_health_url", "")).strip()
    if server_url and urllib.parse.urlsplit(server_url).scheme not in {"http", "https"}:
        raise ValueError("server_health_url must use http or https")
    timestamp_fields = config.get("server_timestamp_fields")
    if not isinstance(timestamp_fields, list) or not all(
        isinstance(field, str) and field.strip() for field in timestamp_fields
    ):
        raise ValueError("server_timestamp_fields must be a list of field names")


def _read_text(path: str, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8").strip("\x00\n ")
    except OSError:
        return default


def boot_id() -> str:
    return _read_text("/proc/sys/kernel/random/boot_id", "unknown")


def _parse_systemd_usec(value: Any) -> int:
    """Parse systemctl's raw integer or human-readable timespan as microseconds."""

    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    factors = {
        "us": 1,
        "ms": 1_000,
        "s": 1_000_000,
        "min": 60_000_000,
        "h": 3_600_000_000,
        "d": 86_400_000_000,
    }
    matches = list(re.finditer(r"(\d+(?:\.\d+)?)\s*(us|ms|min|s|h|d)", text))
    remainder = re.sub(r"(\d+(?:\.\d+)?)\s*(us|ms|min|s|h|d)", "", text)
    if not matches or remainder.strip():
        return 0
    return max(
        0,
        int(sum(float(match.group(1)) * factors[match.group(2)] for match in matches)),
    )


def _parse_timestamp(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def collect_service_status(
    config: dict[str, Any],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    properties = (
        "Type,NotifyAccess,WatchdogUSec,Restart,ActiveState,SubState,MainPID,"
        "NRestarts,ExecMainStatus,Result,ExecMainStartTimestampMonotonic,"
        "RestartUSec,TimeoutStartUSec,TimeoutStopUSec,StartLimitIntervalUSec,"
        "StartLimitBurst,StartLimitAction"
    )
    command = [
        str(config["systemctl_path"]),
        "show",
        str(config["service_name"]),
        f"--property={properties}",
    ]
    try:
        completed = runner(
            command, capture_output=True, text=True, timeout=4, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"reachable": False, "error": str(error)}
    values: dict[str, Any] = {"reachable": completed.returncode == 0}
    for line in completed.stdout.splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    for key in ("MainPID", "NRestarts", "ExecMainStatus", "StartLimitBurst"):
        try:
            values[key] = int(values.get(key, 0))
        except (TypeError, ValueError):
            values[key] = 0
    for key in (
        "WatchdogUSec",
        "RestartUSec",
        "TimeoutStartUSec",
        "TimeoutStopUSec",
        "StartLimitIntervalUSec",
    ):
        values[key] = _parse_systemd_usec(values.get(key))
    try:
        started = int(values.get("ExecMainStartTimestampMonotonic", 0)) / 1_000_000
        uptime = float(_read_text("/proc/uptime", "0").split()[0])
        values["service_age_seconds"] = max(0.0, uptime - started) if started else None
    except (ValueError, IndexError):
        values["service_age_seconds"] = None
    if completed.returncode != 0:
        values["error"] = completed.stderr.strip()[:240]
    return values


def _count_d_state_processes(proc_root: Path = Path("/proc")) -> tuple[int, list[int]]:
    count = 0
    examples: list[int] = []
    try:
        entries = proc_root.iterdir()
    except OSError:
        return 0, []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
            closing = stat.rfind(")")
            state = stat[closing + 2 :].split(None, 1)[0]
        except (OSError, IndexError):
            continue
        if state == "D":
            count += 1
            if len(examples) < 8:
                examples.append(int(entry.name))
    return count, examples


def _parse_key_values(path: str) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        parts = line.replace(":", " ").split()
        if len(parts) >= 2:
            try:
                values[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return values


def _psi_full_avg10(path: str) -> Optional[float]:
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if not line.startswith("full "):
            continue
        for field in line.split()[1:]:
            key, _, value = field.partition("=")
            if key == "avg10":
                try:
                    return float(value) / 100
                except ValueError:
                    return None
    return None


def collect_host_sample(
    now: float, previous: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    meminfo = _parse_key_values("/proc/meminfo")
    vmstat = _parse_key_values("/proc/vmstat")
    try:
        cpu = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()
        cpu_values = [int(value) for value in cpu[1:]]
    except (OSError, IndexError, ValueError):
        cpu_values = []
    cpu_total = sum(cpu_values)
    cpu_iowait = cpu_values[4] if len(cpu_values) > 4 else 0
    swap_total = meminfo.get("SwapTotal", 0)
    swap_used = max(0, swap_total - meminfo.get("SwapFree", 0))
    d_count, d_examples = _count_d_state_processes()
    sample: dict[str, Any] = {
        "sampled_at": now,
        "mem_available_mb": meminfo.get("MemAvailable", 0) / 1024,
        "swap_used_ratio": swap_used / swap_total if swap_total else 0.0,
        "pswpin": vmstat.get("pswpin", 0),
        "pswpout": vmstat.get("pswpout", 0),
        "cpu_total": cpu_total,
        "cpu_iowait": cpu_iowait,
        "d_state_processes": d_count,
        "d_state_examples": d_examples,
        "memory_psi_full_avg10": _psi_full_avg10("/proc/pressure/memory"),
        "io_psi_full_avg10": _psi_full_avg10("/proc/pressure/io"),
        "swapin_pages_per_second": 0.0,
        "swapout_pages_per_second": 0.0,
        "iowait_ratio": 0.0,
    }
    if previous:
        elapsed = max(0.001, now - float(previous.get("sampled_at", now)))
        sample["swapin_pages_per_second"] = max(
            0.0, (sample["pswpin"] - int(previous.get("pswpin", 0))) / elapsed
        )
        sample["swapout_pages_per_second"] = max(
            0.0, (sample["pswpout"] - int(previous.get("pswpout", 0))) / elapsed
        )
        cpu_delta = sample["cpu_total"] - int(previous.get("cpu_total", 0))
        iowait_delta = sample["cpu_iowait"] - int(previous.get("cpu_iowait", 0))
        if cpu_delta > 0:
            sample["iowait_ratio"] = max(0.0, iowait_delta / cpu_delta)
    return sample


def classify_host(config: dict[str, Any], sample: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if sample["d_state_processes"] > int(config["max_d_state_processes"]):
        reasons.append("d_state_processes")
    if sample["swap_used_ratio"] >= float(config["high_swap_used_ratio"]) and sample[
        "mem_available_mb"
    ] <= float(config["min_available_memory_mb"]):
        reasons.append("swap_full_low_memory")
    if sample["iowait_ratio"] >= float(config["max_iowait_ratio"]):
        reasons.append("high_iowait")
    if (
        sample["swapout_pages_per_second"]
        >= float(config["max_swapout_pages_per_second"])
        and sample["iowait_ratio"] >= 0.15
    ):
        reasons.append("swapout_io_pressure")
    if (sample.get("memory_psi_full_avg10") or 0) >= 0.2:
        reasons.append("memory_psi_full")
    if (sample.get("io_psi_full_avg10") or 0) >= 0.2:
        reasons.append("io_psi_full")
    sample["distress"] = bool(reasons)
    sample["distress_reasons"] = reasons
    return sample


def collect_client_health(
    config: dict[str, Any], now: float, runtime: dict[str, Any]
) -> dict[str, Any]:
    path = str(config["client_health_path"])
    payload = _read_json(path, {})
    available = payload.get("schema_version") == SCHEMA_VERSION
    last_success = (
        _parse_timestamp(payload.get("last_success_at")) if available else None
    )
    last_error = _parse_timestamp(payload.get("last_error_at")) if available else None
    unresolved_error = bool(
        last_error and (not last_success or last_error > last_success)
    )
    age = max(0.0, now - last_success) if last_success is not None else None
    fresh = bool(
        available
        and payload.get("state") == "healthy"
        and age is not None
        and age <= float(config["client_max_age_seconds"])
        and not unresolved_error
    )
    sequence = payload.get("sequence") if available else None
    sequence_advanced = sequence is not None and sequence != runtime.get(
        "last_sequence"
    )
    if sequence_advanced:
        runtime["last_sequence"] = sequence
        runtime["last_sequence_advance_at"] = now

    debug_fallback = False
    debug_age: Optional[float] = None
    if not available and config.get("legacy_debug_png_enabled"):
        try:
            png_mtime = Path(str(config["debug_png_path"])).stat().st_mtime
            debug_age = max(0.0, now - png_mtime)
            debug_fallback = debug_age <= float(config["debug_png_max_age_seconds"])
            png_token = int(png_mtime * 1_000_000_000)
            if png_token != runtime.get("last_png_token"):
                runtime["last_png_token"] = png_token
                runtime["last_png_advance_at"] = now
        except OSError:
            pass
    return {
        "available": available,
        "fresh": fresh or debug_fallback,
        "display_success_fresh": fresh,
        "debug_fallback": debug_fallback,
        "debug_age_seconds": debug_age,
        "sequence": sequence,
        "role": payload.get("role") if available else None,
        "state": payload.get("state") if available else None,
        "etag": payload.get("etag") if available else None,
        "error": payload.get("error") if available else None,
        "last_attempt_at": payload.get("last_attempt_at") if available else None,
        "last_success_at": payload.get("last_success_at") if available else None,
        "last_error_at": payload.get("last_error_at") if available else None,
        "sequence_advanced": sequence_advanced,
        "last_success_age_seconds": age,
        "unresolved_error": unresolved_error,
        "in_progress": bool(payload.get("in_progress")) if available else False,
        "pid": payload.get("pid") if available else None,
        "boot_id": payload.get("boot_id") if available else None,
        "server_generated_at": (
            payload.get("server_generated_at") if available else None
        ),
        "server_received_at": payload.get("server_received_at") if available else None,
        "frame_source_created_at": (
            payload.get("frame_source_created_at") if available else None
        ),
    }


def _extract_timestamp(payload: dict[str, Any], fields: list[str]) -> Optional[float]:
    for field in fields:
        value: Any = payload
        for component in field.split("."):
            if not isinstance(value, dict) or component not in value:
                value = None
                break
            value = value[component]
        parsed = _parse_timestamp(value)
        if parsed is not None:
            return parsed
    return None


def collect_server_health(
    config: dict[str, Any], now: float, runtime: dict[str, Any]
) -> dict[str, Any]:
    path = str(config.get("server_health_path", "")).strip()
    url = str(config.get("server_health_url", "")).strip()
    if not path and not url:
        return {"configured": False, "reachable": None, "fresh": None}

    payload: dict[str, Any] = {}
    token: Optional[str] = None
    error: Optional[str] = None
    try:
        if path:
            raw = Path(path).read_text(encoding="utf-8")
            payload = json.loads(raw)
            token = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        else:
            if urllib.parse.urlsplit(url).scheme.lower() not in {"http", "https"}:
                raise ValueError("unsupported server health URL scheme")
            request = urllib.request.Request(
                url, headers={"Accept": "application/json"}
            )
            with urllib.request.urlopen(
                request, timeout=float(config["server_timeout_seconds"])
            ) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise ValueError("server health response exceeds 64 KiB")
                payload = json.loads(raw.decode("utf-8")) if raw else {}
                token = response.headers.get("ETag") or response.headers.get(
                    "X-Frame-Sequence"
                )
                header_generated = response.headers.get("X-Generated-At")
                if header_generated and "generated_at" not in payload:
                    payload["generated_at"] = header_generated
        if not isinstance(payload, dict):
            raise ValueError("server health payload is not an object")
    except (OSError, ValueError, json.JSONDecodeError) as caught:
        # urllib exceptions may embed a credential-bearing URL.  The error
        # class is enough for metrics/status without leaking configuration.
        error = type(caught).__name__

    if token and token != runtime.get("last_server_token"):
        runtime["last_server_token"] = token
        runtime["last_server_advance_at"] = now
    generated_at = _extract_timestamp(
        payload, list(config.get("server_timestamp_fields", []))
    )
    if generated_at is None and token:
        generated_at = runtime.get("last_server_advance_at")
    age = max(0.0, now - generated_at) if generated_at is not None else None
    payload_status = str(payload.get("status", "")).strip().lower()
    payload_healthy = (
        payload_status in {"ok", "ready", "healthy"}
        if payload_status
        else payload.get("healthy", payload.get("ok", True)) is not False
    )
    reachable = error is None
    fresh = bool(
        reachable
        and payload_healthy
        and age is not None
        and age <= float(config["server_max_age_seconds"])
    )
    return {
        "configured": True,
        "reachable": reachable,
        "fresh": fresh,
        "age_seconds": age,
        "token": token,
        "error": error,
    }


def server_health_from_client(
    config: dict[str, Any], now: float, client: dict[str, Any]
) -> dict[str, Any]:
    generated_at = _parse_timestamp(client.get("server_generated_at"))
    received_at = _parse_timestamp(client.get("server_received_at"))
    if generated_at is None and received_at is None:
        return {"configured": False, "reachable": None, "fresh": None}
    age = max(0.0, now - generated_at) if generated_at is not None else None
    return {
        "configured": True,
        "reachable": received_at is not None,
        "fresh": bool(
            received_at is not None
            and age is not None
            and age <= float(config["server_max_age_seconds"])
        ),
        "age_seconds": age,
        "token": None,
        "error": None,
        "source": "client_health",
    }


def _budget_status(
    config: dict[str, Any], now: float, persistent: dict[str, Any], current_boot: str
) -> dict[str, Any]:
    window_start = now - float(config["cycle_window_seconds"])
    timestamps = []
    for value in persistent.get("restart_timestamps", []):
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            continue
        if timestamp >= window_start:
            timestamps.append(timestamp)
    persistent["restart_timestamps"] = timestamps
    try:
        boot_count = int(persistent.get("boot_restart_count", 0))
    except (TypeError, ValueError):
        boot_count = 0
    if persistent.get("boot_id") != current_boot:
        boot_count = 0
    last_restart = max(timestamps) if timestamps else None
    cooldown_remaining = (
        max(0.0, float(config["cooldown_seconds"]) - (now - last_restart))
        if last_restart is not None
        else 0.0
    )
    window_remaining = max(0, int(config["max_restarts_per_window"]) - len(timestamps))
    boot_remaining = max(0, int(config["max_restarts_per_boot"]) - boot_count)
    return {
        "window_remaining": window_remaining,
        "boot_remaining": boot_remaining,
        "cooldown_remaining_seconds": cooldown_remaining,
        "allowed": window_remaining > 0
        and boot_remaining > 0
        and cooldown_remaining == 0,
    }


def assess(
    config: dict[str, Any],
    now: float,
    service: dict[str, Any],
    host: dict[str, Any],
    client: dict[str, Any],
    server: dict[str, Any],
    runtime: dict[str, Any],
    persistent: dict[str, Any],
    current_boot: str,
) -> dict[str, Any]:
    active = (
        service.get("reachable", False)
        and service.get("ActiveState") == "active"
        and int(service.get("MainPID", 0)) > 0
    )
    manager_recovery = service.get("SubState") == "auto-restart" or service.get(
        "ActiveState"
    ) in {"activating", "deactivating"}
    service_age = service.get("service_age_seconds")
    pid = int(service.get("MainPID", 0))
    if pid and pid != runtime.get("last_main_pid"):
        runtime["last_main_pid"] = pid
        runtime["main_pid_changed_at"] = now
    pid_age = now - float(runtime.get("main_pid_changed_at", now))
    startup_grace = manager_recovery or (
        active
        and (
            (
                service_age is not None
                and service_age < float(config["startup_grace_seconds"])
            )
            or pid_age < float(config["startup_grace_seconds"])
        )
    )
    systemd_guarded = (
        service.get("Type") == "notify"
        and service.get("NotifyAccess") == "main"
        and int(service.get("WatchdogUSec", 0)) > 0
    )
    split_client_target = str(config["service_name"]) == SPLIT_CLIENT_SERVICE
    contract_expectations = {
        "Type": "notify",
        "NotifyAccess": "main",
        "WatchdogUSec": 45_000_000,
        "Restart": "on-failure",
        "RestartUSec": 10_000_000,
        "TimeoutStartUSec": 60_000_000,
        "TimeoutStopUSec": 30_000_000,
        "StartLimitIntervalUSec": 21_600_000_000,
        "StartLimitBurst": 3,
        "StartLimitAction": "none",
    }
    contract_mismatches = [
        key
        for key, expected in contract_expectations.items()
        if service.get(key) != expected
    ]
    contract_matches = not split_client_target or not contract_mismatches
    client_identity_matches = True
    if client.get("available"):
        client_identity_matches = (
            client.get("role") == "display-client"
            and client.get("boot_id") == current_boot
        )
        if systemd_guarded:
            client_identity_matches = client_identity_matches and int(
                client.get("pid") or 0
            ) == int(service.get("MainPID", 0))
        if not client_identity_matches:
            client["fresh"] = False
            client["display_success_fresh"] = False
    client["identity_matches"] = client_identity_matches

    budget = _budget_status(config, now, persistent, current_boot)
    systemd_budget_exhausted = systemd_guarded and (
        budget["window_remaining"] == 0 or budget["boot_remaining"] == 0
    )
    guarded_unhealthy = not active or not client.get("fresh")

    if host.get("distress"):
        classification = "host_kernel_storage_distress"
    elif manager_recovery:
        classification = "service_manager_recovery"
    elif active and split_client_target and not contract_matches:
        classification = "systemd_contract_mismatch"
    elif startup_grace and not client.get("fresh"):
        classification = "startup_grace"
    elif systemd_budget_exhausted and guarded_unhealthy:
        classification = "systemd_restart_budget_exhausted"
    elif not active:
        classification = "service_failure"
    elif server.get("configured") and not server.get("fresh"):
        classification = "server_network_distress"
    elif not client.get("fresh"):
        classification = (
            "client_unhealthy_systemd_guarded" if systemd_guarded else "render_failure"
        )
    else:
        classification = "healthy"

    fallback_failure = (
        classification in {"service_failure", "render_failure"}
        and not split_client_target
        and not systemd_guarded
    )
    consecutive = int(runtime.get("consecutive_failures", 0))
    consecutive = consecutive + 1 if fallback_failure else 0
    runtime["consecutive_failures"] = consecutive
    threshold_met = consecutive >= int(config["consecutive_failures"])
    recovery_requested = bool(
        config.get("recovery_enabled")
        and fallback_failure
        and threshold_met
        and budget["allowed"]
        and not host.get("distress")
        and not manager_recovery
    )
    budget_exhausted = fallback_failure and threshold_met and not budget["allowed"]
    human_escalation = (
        classification
        in {
            "host_kernel_storage_distress",
            "server_network_distress",
            "systemd_contract_mismatch",
            "systemd_restart_budget_exhausted",
        }
        or budget_exhausted
        or (
            classification == "service_failure"
            and (split_client_target or systemd_guarded)
        )
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": now,
        "classification": classification,
        "healthy": classification == "healthy",
        "service_active": active,
        "systemd_watchdog_primary": systemd_guarded,
        "split_client_target": split_client_target,
        "systemd_contract_matches": contract_matches,
        "systemd_contract_mismatches": contract_mismatches,
        "startup_grace": startup_grace,
        "consecutive_failures": consecutive,
        "fallback_recovery_requested": recovery_requested,
        "recovery_budget_exhausted": budget_exhausted,
        "human_escalation": human_escalation,
        "budget": budget,
        "service": service,
        "host": host,
        "client": client,
        "server": server,
    }


def restart_client_service(
    config: dict[str, Any],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    service = str(config["service_name"])
    if not SERVICE_NAME_PATTERN.fullmatch(service):
        return False, "unsafe service name"
    command = [str(config["systemctl_path"]), "restart", "--no-block", service]
    try:
        completed = runner(
            command, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)[:240]
    detail = (completed.stderr or completed.stdout).strip()[:240]
    return completed.returncode == 0, detail


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def physical_identity() -> dict[str, str]:
    return {
        "hostname": socket.gethostname(),
        "machine_id_sha256": _hash_text(_read_text("/etc/machine-id")),
        "hardware_model": _read_text("/proc/device-tree/model"),
        "device_tree_serial_sha256": _hash_text(
            _read_text("/proc/device-tree/serial-number")
        ),
    }


def exact_physical_target_matches(
    expected: dict[str, str], actual: dict[str, str]
) -> bool:
    required = ("hostname", "machine_id_sha256", "hardware_model")
    if any(not str(expected.get(key, "")).strip() for key in required):
        return False
    for key in required:
        if expected[key] != actual.get(key):
            return False
    expected_serial = str(expected.get("device_tree_serial_sha256", "")).strip()
    return not expected_serial or expected_serial == actual.get(
        "device_tree_serial_sha256"
    )


def _record_restart(
    persistent: dict[str, Any], now: float, current_boot: str, count: int = 1
) -> None:
    if persistent.get("boot_id") != current_boot:
        persistent["boot_id"] = current_boot
        persistent["boot_restart_count"] = 0
    try:
        boot_restart_count = int(persistent.get("boot_restart_count", 0))
    except (TypeError, ValueError):
        boot_restart_count = 0
    try:
        total_restart_count = int(persistent.get("total_restart_count", 0))
    except (TypeError, ValueError):
        total_restart_count = 0
    persistent["boot_restart_count"] = boot_restart_count + count
    persistent["total_restart_count"] = total_restart_count + count
    timestamps = list(persistent.get("restart_timestamps", []))
    timestamps.extend([now] * count)
    persistent["restart_timestamps"] = timestamps[-100:]
    persistent["last_restart_at"] = now


def _reconcile_systemd_restarts(
    service: dict[str, Any],
    runtime: dict[str, Any],
    persistent: dict[str, Any],
    now: float,
    current_boot: str,
) -> bool:
    current = int(service.get("NRestarts", 0))
    previous = runtime.get("last_nrestarts")
    runtime["last_nrestarts"] = current
    try:
        previous_count = int(previous)
    except (TypeError, ValueError):
        return False
    if current <= previous_count:
        return False
    _record_restart(persistent, now, current_boot, min(10, current - previous_count))
    return True


def _metrics(result: dict[str, Any], persistent: dict[str, Any]) -> str:
    host = result["host"]
    client = result["client"]
    server = result["server"]
    budget = result["budget"]
    classification = result["classification"].replace('"', "")
    display_success_fresh = int(bool(client.get("display_success_fresh")))
    sequence_advanced = int(bool(client.get("sequence_advanced")))
    swapout_rate = host.get("swapout_pages_per_second", 0)
    restart_total = int(persistent.get("total_restart_count", 0))
    reboot_recommendation = int(result.get("reboot_recommendation", False))
    contract_matches = int(result["systemd_contract_matches"])
    values = [
        "# HELP display_watchdog_healthy Overall classified health.",
        "# TYPE display_watchdog_healthy gauge",
        f"display_watchdog_healthy {int(result['healthy'])}",
        f'display_watchdog_classification{{state="{classification}"}} 1',
        f"display_watchdog_service_active {int(result['service_active'])}",
        f"display_watchdog_systemd_primary {int(result['systemd_watchdog_primary'])}",
        f"display_watchdog_systemd_contract_matches {contract_matches}",
        f"display_watchdog_client_fresh {int(bool(client.get('fresh')))}",
        f"display_watchdog_display_success_fresh {display_success_fresh}",
        f"display_watchdog_frame_sequence {client.get('sequence') or 0}",
        f"display_watchdog_frame_sequence_advanced {sequence_advanced}",
        f"display_watchdog_server_configured {int(bool(server.get('configured')))}",
        f"display_watchdog_server_fresh {int(bool(server.get('fresh')))}",
        f"display_watchdog_host_distress {int(bool(host.get('distress')))}",
        f"display_watchdog_d_state_processes {host.get('d_state_processes', 0)}",
        f"display_watchdog_swap_used_ratio {host.get('swap_used_ratio', 0):.6f}",
        f"display_watchdog_swapout_pages_per_second {swapout_rate:.6f}",
        f"display_watchdog_iowait_ratio {host.get('iowait_ratio', 0):.6f}",
        f"display_watchdog_consecutive_failures {result['consecutive_failures']}",
        f"display_watchdog_restart_window_remaining {budget['window_remaining']}",
        f"display_watchdog_restart_boot_remaining {budget['boot_remaining']}",
        f"display_watchdog_restart_total {restart_total}",
        f"display_watchdog_human_escalation {int(result['human_escalation'])}",
        f"display_watchdog_reboot_recommendation {reboot_recommendation}",
        f"display_watchdog_last_check_timestamp_seconds {result['checked_at']:.3f}",
    ]
    return "\n".join(values) + "\n"


def run_check(
    config: dict[str, Any],
    *,
    now: Optional[float] = None,
    no_recovery: bool = False,
    quiet_healthy: bool = False,
) -> dict[str, Any]:
    checked_at = time.time() if now is None else now
    runtime = _read_json(str(config["runtime_state_path"]), {})
    persistent = _read_json(str(config["persistent_state_path"]), {})
    service = collect_service_status(config)
    current_boot = boot_id()
    persistent_changed = _reconcile_systemd_restarts(
        service, runtime, persistent, checked_at, current_boot
    )
    host_sample = collect_host_sample(checked_at, runtime.get("host_sample"))
    host = classify_host(config, host_sample)
    runtime["host_sample"] = host_sample
    client = collect_client_health(config, checked_at, runtime)
    server = collect_server_health(config, checked_at, runtime)
    if not server.get("configured"):
        server = server_health_from_client(config, checked_at, client)
    result = assess(
        config,
        checked_at,
        service,
        host,
        client,
        server,
        runtime,
        persistent,
        current_boot,
    )

    action = "none"
    action_detail = ""
    if result["fallback_recovery_requested"] and not no_recovery:
        succeeded, action_detail = restart_client_service(config)
        action = (
            "client_service_restart" if succeeded else "client_service_restart_failed"
        )
        if succeeded:
            _record_restart(persistent, checked_at, current_boot)
            persistent_changed = True
            runtime["consecutive_failures"] = 0
    result["action"] = action
    result["action_detail"] = action_detail

    budget_exhausted = bool(
        result["recovery_budget_exhausted"]
        or result["classification"] == "systemd_restart_budget_exhausted"
    )
    target_matches = exact_physical_target_matches(
        config["physical_target"], physical_identity()
    )
    result["physical_target_proven"] = target_matches
    result["reboot_recommendation"] = bool(
        budget_exhausted
        and config.get("human_reboot_recommendation_enabled")
        and target_matches
    )
    result["previous_classification"] = runtime.get("last_classification")
    transitioned = result["classification"] != runtime.get("last_classification")
    runtime["last_classification"] = result["classification"]

    _write_json(str(config["runtime_state_path"]), runtime, 0o644)
    if persistent_changed:
        _write_json(str(config["persistent_state_path"]), persistent)
    _write_json(str(config["status_path"]), result, 0o644)
    _atomic_write(
        Path(str(config["metrics_path"])), _metrics(result, persistent), 0o644
    )
    if (
        not quiet_healthy
        or transitioned
        or action != "none"
        or result["human_escalation"]
    ):
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return result


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        choices=("check", "validate-config", "print-identity"),
        default="check",
    )
    parser.add_argument(
        "--config",
        default="/etc/display-watchdog/config.json",
        help="JSON configuration path",
    )
    parser.add_argument("--no-recovery", action="store_true")
    parser.add_argument("--quiet-healthy", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.command == "print-identity":
        print(json.dumps(physical_identity(), sort_keys=True, indent=2))
        return 0
    try:
        config = load_config(arguments.config)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if arguments.command == "validate-config":
        print(f"valid: {arguments.config}")
        return 0
    run_check(
        config,
        no_recovery=arguments.no_recovery,
        quiet_healthy=arguments.quiet_healthy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
