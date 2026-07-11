# Screen ownership arbiter

The scheduled transit, weather, or token screen is the base display. Optional
plugins must claim the screen through `ScreenArbiter` before rendering an
interrupting view.

A claim has four properties:

- `owner`: a stable, unique plugin name;
- `priority`: a larger number wins;
- `ttl_seconds`: a mandatory expiry that prevents a failed plugin from holding
  the display indefinitely;
- `exclusive`: when true, a winning claim cannot be pre-empted before it is
  released or expires.

Claims remain registered while another plugin is active. When the winning claim
ends, the next-highest claim becomes eligible automatically; if no claims
remain, the normal scheduled display is restored.

The arbiter manages ownership, not a retained image layer. An e-ink panel keeps
showing the last pixels written by the previous owner until the resumed plugin
renders again. Interrupting plugins must therefore detect when
`can_render(owner)` becomes true and redraw immediately, or poll frequently
enough for their use case. The built-in flight and ISS plugins update
periodically, while the display manager explicitly redraws the base screen when
the final claim ends.

## Existing plugin priorities

Flights default to priority `50`. ISS defaults to `60` when the existing
`iss_priority=true` setting is used, or `40` when it is false. Set
`screen_priority_flight` or `screen_priority_iss` to override those values.

Future plugins should use bounded claims and check `can_render(owner)` again
while holding the display lock immediately before writing to the device.

The RSS watcher defaults to priority `30`: it interrupts the scheduled base
screen and calendar agenda glances, but yields to upcoming calendar events,
flights, and the priority ISS view. Set `rss_watch_priority` to change this.
