# Display client watchdog and secondary health auditor

The watchdog is a layered, client-only recovery design for the constrained
display Raspberry Pi. It does not reboot, shut down, power-cycle, or control a
smart plug. Host distress and upstream failure are escalation conditions, not
reasons to restart more aggressively.

Older setup/update scripts configured Linux `/dev/watchdog` with a 15-second
timeout and load thresholds, while the startup scripts disabled the same
service. This was contradictory and unsafe: swap or I/O distress can raise load
without proving an application failure, turning the known Pi pressure mode into
a host reboot. The setup/update paths no longer install, enable, configure, or
toggle that hardware watchdog. Existing installations can remove the legacy
configuration with the main uninstall script after a separately approved live
change; this candidate does not mutate it.

## Detection and recovery layers

The split client architecture owns systemd notify semantics as its primary hang
detector:

- `display-client.service` uses `Type=notify`, `NotifyAccess=main`, and
  `WatchdogSec=45`.
- Its unit bounds starts with `StartLimitIntervalSec=6h`,
  `StartLimitBurst=3`, and `StartLimitAction=none`; service recovery uses
  `Restart=on-failure`, `RestartSec=10`, `TimeoutStartSec=60`, and
  `TimeoutStopSec=30`.
- Its main loop sends `READY=1` only after hardware initialization and the first
  successful fresh `200` or `304` frame response.
- That same main loop sends `WATCHDOG=1` only after each subsequent successful
  fresh `200` or `304`. A `200` succeeds only after the display update; a `304`
  preserves the already-verified frame.
- No helper or timer sends keepalives. A client thread wedged in rendering,
  lock acquisition, SPI, or I/O therefore cannot be hidden by a healthy helper.
- Clean shutdown does not clear the e-paper. Whole-host `RuntimeWatchdogSec`,
  hardware watchdog activation, reboot, and power actions are not configured.

The architecture change owns the client implementation and unit. This candidate
does not supply another notifier, client unit, or keepalive path. The current
monolith can retain `display.service` during migration.

The optional minute-level `display-watchdog.timer` is a secondary auditor, not
the split client's watchdog. It is not installed unless the setup script is run,
and automatic fallback recovery remains disabled by default. It checks:

- systemd main PID, active/sub states, exit status, `NRestarts`, and whether the
  client is actually notify/watchdog guarded;
- the tmpfs client state, sequence, ETag, last successful fresh response, and
  matching boot ID/main PID;
- optional server JSON or HTTP freshness, including timestamps, ETag, or frame
  sequence metadata;
- D-state tasks, available memory, swap occupancy and swap-in/out deltas, CPU
  I/O wait, and PSI when the kernel exposes it;
- an opt-in legacy debug PNG fallback during monolith migration.

The auditor classifies a failure before acting:

| Classification | Meaning | Automatic fallback action |
| --- | --- | --- |
| `healthy` | Client, frame, host, and configured server are fresh | None |
| `startup_grace` | New client PID is inside bounded warm-up | None |
| `client_unhealthy_systemd_guarded` | Split client is stale; systemd watchdog owns it | None |
| `systemd_contract_mismatch` | Installed split-client unit differs from the exact bounded notify contract | Human escalation; no auditor restart |
| `systemd_restart_budget_exhausted` | Notify client is unhealthy after its observed restart budget is consumed | Human escalation; no auditor restart |
| `render_failure` | Legacy client is active but its render evidence is stale | Optional client-service restart |
| `service_failure` | Service is stably failed, not auto-restarting | Optional restart only for a legacy non-notify service; otherwise escalation |
| `service_manager_recovery` | systemd is already activating/restarting it | None |
| `server_network_distress` | Configured upstream is unreachable or stale | Human escalation; no client restart |
| `host_kernel_storage_distress` | D-state, swap/memory, PSI, or I/O gate tripped | Human escalation; no restart |

The auditor never restarts `display-client.service` or another
notify/watchdog-guarded client, even if recovery is enabled; systemd remains the
sole restart owner. Its `/run` JSON and this auditor are observation-only for
the split architecture. The legacy restart path is
disabled by default. When enabled, it still requires
three consecutive eligible failures, a 15-minute cooldown, at most two restarts
per six hours, and at most three per boot. Observed systemd `NRestarts` increases
also consume the persistent budget. The only command available to the auditor
is `systemctl restart --no-block <configured-client.service>`.

## Runtime contract

The split client may publish this versioned diagnostic contract atomically after
state or sequence changes:

```json
{
  "schema_version": 1,
  "role": "display-client",
  "boot_id": "...",
  "pid": 123,
  "state": "healthy",
  "sequence": 42,
  "etag": "\"frame-42\"",
  "last_attempt_at": "2026-07-15T18:20:00+00:00",
  "last_success_at": "2026-07-15T18:20:01+00:00",
  "last_error_at": null,
  "error": null,
  "frame_source_created_at": "2026-07-15T18:19:58+00:00",
  "server_generated_at": "2026-07-15T18:19:58+00:00",
  "server_received_at": "2026-07-15T18:20:01+00:00"
}
```

The default path is `/run/rpi-waiting-time-display/client-health.json`; a blank
client health path disables it. The file is diagnostic-only and `/run` is
tmpfs, so frame health never writes to the checkout, `/var`, or the SD card.

The split server exposes `/healthz` with
`status/service/sequence/generated_at`. Its independent `/readyz` freshness
gate returns `status/sequence/published_at` and a non-2xx response for a stale
or absent frame. Configure `server_health_url` to `/readyz` for the strongest
live check. The auditor accepts `generated_at`, `published_at`,
`server_generated_at`, `updated_at`, `last_success_at`, or `timestamp` by
default. For HTTP it also understands `ETag`,
`X-Frame-Sequence`, and `X-Generated-At`. Server freshness remains separate
from client/display freshness so an upstream or network outage does not cause a
client restart.

On physical hardware, the debug image defaults to
`/run/rpi-waiting-time-display/debug_output.png` and is limited to one save per
five seconds. A persistent debug path is possible only through the explicit
`debug_image_path` setting. Mock displays retain `./debug_output.png` for local
tests and feature screenshots.

## Optional install in observe-only mode

Review the templates first. Installation enables the audit timer but does not
restart the display service:

```bash
sudo docs/service/setup_display_watchdog.sh
systemctl status display-watchdog.timer
python3 /usr/local/lib/display-watchdog/display_watchdog.py check \
  --config /etc/display-watchdog/config.json --no-recovery
```

The default target is `display-client.service`. The installer reports whether
`Type=notify`, `NotifyAccess=main`, and a nonzero watchdog interval are active,
but it never restarts the target service.

Only a deliberate migration decision should enable the auditor's legacy
fallback:

```bash
sudo docs/service/setup_display_watchdog.sh \
  --service display.service --enable-legacy-recovery
```

Existing `/etc/display-watchdog/config.json` is never overwritten. Edit it
explicitly to add a server path/URL or tune freshness thresholds. Keep recovery
off through the initial observation period.

## Logs, status, and metrics

The timer logs only health transitions, actions, and escalations to the journal:

```bash
journalctl -u display-watchdog.service
cat /run/display-watchdog/status.json
cat /run/display-watchdog/metrics.prom
systemctl show display-client.service \
  -p Type -p NotifyAccess -p WatchdogUSec -p ActiveState -p MainPID -p NRestarts
```

Prometheus text metrics include the classification, client and server
freshness, sequence advancement, D-state count, swap ratio/rate, I/O wait,
restart budgets, escalation state, and a reboot-recommendation gauge.

The reboot gauge defaults to zero. It can become one only after the cycle budget
is exhausted, a human-only recommendation is explicitly enabled, and hostname,
machine-ID SHA-256, and exact hardware model all match the configured physical
target. A device-tree serial hash may add a fourth proof. Even then the program
only reports a recommendation; it has no reboot or power action. Generate the
non-secret proof values locally with:

```bash
python3 /usr/local/lib/display-watchdog/display_watchdog.py print-identity
```

## Rollback and uninstall

To stop all checks while preserving evidence:

```bash
sudo systemctl disable --now display-watchdog.timer
```

To remove the timer, auditor, and display-service runtime-directory drop-in without
restarting the display:

```bash
sudo docs/service/uninstall_display_watchdog.sh
```

For the migration monolith, pass `--service display.service`. Configuration and
persistent recovery history are retained by default. Add `--purge` only after
capturing any needed evidence. The uninstaller never removes or replaces the
architecture-owned client unit.

## Resource and write budget

- The auditor is a short-lived, standard-library-only Python oneshot every 60
  seconds; no monitoring daemon remains resident.
- systemd enforces `MemoryHigh=32M`, `MemoryMax=48M`, `CPUQuota=20%`, idle I/O
  scheduling, and a 20-second execution timeout.
- Per-check observations, status, metrics, and optional client diagnostics live
  only in `/run`. Persistent recovery state changes only when a restart is
  requested or a new systemd restart is observed.
- Auditor observations, status, and metrics are installed as `0644` for local
  diagnostics/scraping; persistent recovery history remains root-only `0600`.
- Healthy checks are quiet, avoiding one journal entry per minute.
- The system remains compatible with kernels that do not expose PSI; `/proc`
  swap, CPU, process-state, and memory deltas remain authoritative.

An indicative macOS arm64 development measurement of an observe-only collection
path on 2026-07-15 took 0.18 seconds wall time, reported 26,492,928 bytes maximum
RSS (about 25.3 MiB), zero swaps, and zero block-input/output operations. That
is evidence for the candidate's systemd limits, not a substitute for the
device-side gate below; macOS lacks the target's `/proc` and systemd surfaces.

Before deployment on a Pi Zero, measure the candidate in observe-only mode:

```bash
/usr/bin/time -v python3 /usr/local/lib/display-watchdog/display_watchdog.py \
  check --config /etc/display-watchdog/config.json --no-recovery --quiet-healthy
systemd-run --wait --pipe -p MemoryMax=48M \
  /usr/bin/python3 /usr/local/lib/display-watchdog/display_watchdog.py \
  check --config /etc/display-watchdog/config.json --no-recovery
```

That device-side measurement is intentionally a deployment gate; this change
does not touch the currently wedged physical Pi.
