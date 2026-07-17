# Split render server and display client

The split architecture moves every network/data task off the e-paper Pi. The
render server runs the existing `DisplayManager`, including transit, weather,
flights, ISS, schedules, screen arbitration, display overrides, and all public
or private plugins. Instead of touching GPIO, it atomically publishes the exact
`250x120` PNG that the display would show. The client only polls, validates,
rotates that PNG back into the hardware buffer orientation, and updates the
panel.

This is an additional deployment mode. `basic.py` remains the monolith entrypoint
for rollback and existing installations. The plugin interfaces and untracked
`.env` configuration remain unchanged; private modules should be integrated
into the server's private deployment branch exactly as they are for the
monolith. The client needs no household API credentials—only the frame URL and,
when configured, its bearer token.

## Wire contract

- `GET /healthz`: process liveness plus the current sequence/generated time.
- `GET /readyz`: `200` only while a verified frame exists and is younger than
  `display_server_ready_max_age`; otherwise `503` with `no-frame` or
  `stale-frame`.
- `GET /api/v1/status`: authenticated frame metadata.
- `GET /api/v1/frame.png`: authenticated exact-size PNG.
- Frame responses include `ETag`, `X-Display-Sequence`,
  `X-Display-Published-At`, and `X-Display-SHA256`. `If-None-Match` returns
  `304`, so a one-second poll interval does not retransmit unchanged images.

Publication uses `fsync` plus atomic `os.replace` for both `latest.png` and its
JSON commit marker. The API only exposes an in-memory snapshot after both
replacements succeed. The client rejects wrong content types, invalid or
oversized PNGs, non-`250x120` dimensions, digest/length mismatches, stale or
future timestamps, and backward sequences without a newer server epoch.

When the network or server is briefly unavailable, the client keeps the last
verified pixels. After a bounded local outage threshold it replaces those
pixels with a tiny locally generated diagnostic containing only local time,
time since the last success when known, and a stable error category. It never
displays an HTTP error body. Retained last-verified pixels may age in place, but
the client never accepts or renders a newly arrived response unless it is
verified and fresh. The next verified server response restores the verified
frame immediately, including a `304` for the in-memory last verified frame.

## Security model

The default server bind is loopback. A non-loopback bind refuses to start
without `display_server_token`, unless an operator explicitly sets
`display_server_allow_unauthenticated=true`. Use a long random token, keep it
only in each host's ignored mode-`0600` `.env`, and restrict port 8787 to the
display VLAN/client with a host firewall. Bearer auth does not encrypt traffic;
use an isolated trusted LAN, WireGuard/Tailscale, or a TLS reverse proxy across
untrusted networks. Do not embed credentials in the image, container, Compose
file, service unit, repository URL, or command line.

Health endpoints intentionally contain only sequence/timestamp data and do not
require auth. The frame and status endpoints do.

## Server setup

Copy `.env.example` to `.env`, retain the normal feature configuration, then
set at least:

```dotenv
display_server_host=0.0.0.0
display_server_port=8787
display_server_token=replace-with-a-random-secret
display_server_ready_max_age=300
```

Native Linux:

```bash
sudo ./docs/service/install_split_role.sh server
sudo systemctl enable --now display-render-server.service
curl http://127.0.0.1:8787/healthz
curl http://127.0.0.1:8787/readyz
```

The installer stages by default. Add `--activate` only when the deployment
coordinator has granted the slot. It never copies `.env` secrets into Git.

Production container:

```bash
docker compose -f compose.server.yml build
docker compose -f compose.server.yml up -d
docker compose -f compose.server.yml exec display-render-server \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8787/readyz').read().decode())"
```

The image runs as UID/GID 10001, read-only, with all Linux capabilities dropped
and tmpfs state at `/run/rpi-waiting-time-display` and `/tmp`. A named
`/app/cache` volume retains bounded plugin state, flight statistics, and
Skyfield ephemeris data across restarts. It logs to stdout/stderr for the
container runtime rather than writing a persistent app log. Supply `.env` at
runtime; it is excluded from the build context.

## Client setup

On the e-paper Pi, keep the hardware settings and configure only:

```dotenv
display_model=epd2in13_V4
screen_rotation=90
display_client_url=http://render-server.local:8787/api/v1/frame.png
display_client_token=the-same-random-secret
display_client_poll_interval=1
display_client_timeout=5
display_client_max_frame_age=300
display_client_full_refresh_every=40
display_client_diagnostic_after=300
display_client_diagnostic_cadence=60
display_client_clock_sync_path=/run/systemd/timesync/synchronized
```

`display_client_diagnostic_after` defaults to five minutes and is bounded to
30 seconds through 24 hours. Shorter failures retain the exact last-good
pixels. `display_client_diagnostic_cadence` defaults to one minute and is
bounded to 30 seconds through one hour; the local frame is not regenerated on
each network poll. Error-category and clock-synchronization changes are
coalesced until that hard cadence allows the next update. The diagnostic uses
only Pillow's built-in bitmap font and local drawing primitives—no assets,
browser, server, extra loop, or network probe.

Threshold and cadence decisions use the monotonic clock, so wall-clock steps
cannot accelerate the transition. By default the client checks the local
systemd-timesyncd marker at
`/run/systemd/timesync/synchronized`. While that marker is absent, the screen
says `Local time: not synchronized` instead of presenting a potentially false
time. Set `display_client_clock_sync_path` to the marker used by the host's
time-sync startup gate, or leave it blank only when that external gate
guarantees synchronization before client startup. Future/stale timestamp
validation remains active either way; the marker does not bypass any frame
check.

Then stage and activate during an approved deployment window:

```bash
sudo ./docs/service/install_split_role.sh client
sudo systemctl disable --now display.service
sudo systemctl enable --now display-client.service
systemctl status display-client.service
```

`display-client.service` uses `Type=notify`, `NotifyAccess=main`, and
`WatchdogSec=45`. Its explicit `StartLimitIntervalSec=6h`,
`StartLimitBurst=3`, and `StartLimitAction=none` budget prevents an unhealthy
client from being restarted indefinitely: after three failed starts or
watchdog terminations in six hours, systemd leaves the client stopped without
escalating to a host action. The main poll loop sends `READY=1` after hardware
initialization and services `WATCHDOG=1` after every completed bounded poll,
including a safely classified rejection. This distinguishes client-loop health
from render-server health: rejected data still cannot alter protocol state or
be displayed, while a server outage no longer creates a client restart loop.
A wedged request or display write still misses the watchdog because there is no
separate helper thread to mask it. Systemd may restart this client service
after a watchdog failure; this project does not configure a whole-host hardware
watchdog, reboot, or power cycle.

The client uses partial updates and establishes a base image on its first
frame. It performs a hardware full/base refresh every
`display_client_full_refresh_every` accepted frames (40 by default) to retain
the monolith's anti-ghosting behavior. Clean shutdown releases the hardware
without clearing the panel, so the last verified pixels remain visible.

Secondary structured diagnostics are atomically written only on sequence/state
changes to `/run/rpi-waiting-time-display/client-health.json` (tmpfs). Schema
version 1 fields are: `role`, `boot_id`, `pid`, `state`, `sequence`, `etag`,
`last_attempt_at`, `last_success_at`, `last_error_at`, `error`,
`frame_source_created_at`, `server_generated_at`, and `server_received_at`.
On failures, `error` is the same sanitized stable category used by the local
diagnostic rather than a URL-bearing exception string.
Set `display_client_health_path=` to disable this secondary file.
An external auditor may read this file and systemd state for diagnostics, but
for a notify-guarded client it must remain observation-only. The service's
systemd watchdog and restart budget are the recovery and loop-prevention
mechanisms.

## Migration and rollback

Use a two-phase migration so the display never depends on an unproven server:

1. Record the current public and private deployment SHAs, current service unit,
   `.env` checksum, and a fresh display photograph/debug image. Create rollback
   refs before changing either host.
2. Deploy the render server first while the monolith continues driving the
   panel. Verify `/healthz`, `/readyz`, authenticated frame download, PNG
   dimensions/digest, sequence advancement, and all private plugin screens.
3. Stage the client and service unit on the display Pi without stopping the
   monolith. Confirm URL/token connectivity from that Pi.
4. In the coordinator-approved window, stop/disable `display.service` and
   enable `display-client.service`. Never run both against the panel.
5. Verify systemd readiness/watchdog status, a fresh sequence, zero restarts,
   the `/run` health JSON, service logs, and the physical `250x120` display.

Rollback is deliberately simple: stop/disable `display-client.service`, restore
the recorded private branch/`.env` if changed, and re-enable the prior
`display.service`. The render server can remain running because it has no GPIO
access, or be stopped independently. A failed client migration does not require
a host reboot. If the Pi shows blocked `D` state, rising swap I/O, storage or
kernel distress, stop recovery attempts and return ownership to the deployment
coordinator; do not restart-loop, reboot, or power-cycle it.

## Release/deployment checklist

- Public PR candidate and release tag point to the exact reviewed commit.
- Server image is built from that commit and its immutable digest recorded.
- Private server lineage contains the public candidate plus every private
  plugin/config boundary; no private files exist in the public PR or image
  build context.
- Server starts without GPIO/Waveshare packages and returns healthy/fresh APIs.
- Authenticated PNG is `250x120`, hash-valid, atomically replaced, and supports
  `ETag`/`304` with a one-second client poll.
- Client contains no collection, scheduling, arbitration, or household API
  credentials and is the only service touching the panel.
- The previous monolith SHA/service and private rollback ref are recorded.
- Coordinator confirms the physical Pi is recovered and grants the deployment
  slot before any RS2/display mutation.
