# Display override API

The optional display override API lets another device on the private network
request a screen for five minutes. The request is an ordinary arbiter claim:
calendar alerts, nearby flights, ISS passes, or any other claim with a higher
configured priority can replace it. When that claim ends, the requested screen
returns for the remainder of its lease.

Enable the listener in the display's untracked `.env` file:

```dotenv
display_override_api_enabled=true
display_override_api_host=0.0.0.0
display_override_api_port=5003
```

The listener defaults to `127.0.0.1`. Set `display_override_api_host` explicitly
to a LAN interface or `0.0.0.0` when another private-network device needs to
connect. Requests are still limited to loopback and private-network client
addresses. For a shared or untrusted LAN, set `display_override_api_token` and
send it as a Bearer token. The default lease is 300 seconds and the default
priority is 30; both can be changed with `display_override_duration_seconds`
and `display_override_priority`.

Request one of `token`, `weather`, `transit`, `calendar`, or `iss` (`codex`
remains an accepted alias for `token`):

```bash
curl -X POST http://DISPLAY_HOST:5003/api/display/token
curl -X POST http://DISPLAY_HOST:5003/api/display/iss
curl -X POST http://DISPLAY_HOST:5003/api/display \
  -H 'Content-Type: application/json' \
  -d '{"module":"weather"}'
```

`token` bypasses the normal recent-activity condition, but still needs a
configured, non-stale token usage source. `calendar` shows the current agenda.
Weather, transit, and calendar similarly need their data sources configured.
A successful request can therefore be accepted without immediately rendering
when data is unavailable or a higher-priority owner controls the screen.

`iss` shows the next future overflight already known to the ISS tracker,
including its start time, countdown, duration, and peak direction/elevation.
It does not make a fresh prediction request on demand. If the tracker is
disabled, still warming up, or has no future cached pass, the screen says that
no prediction is available. A live overhead pass keeps its existing higher
priority and replaces this prediction card until the pass ends.

Inspect or clear the lease with:

```bash
curl http://DISPLAY_HOST:5003/api/display
curl -X DELETE http://DISPLAY_HOST:5003/api/display
```
