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
ends, the next-highest claim resumes automatically; if no claims remain, the
normal scheduled display is restored.

## Existing plugin priorities

Flights default to priority `50`. ISS defaults to `60` when the existing
`iss_priority=true` setting is used, or `40` when it is false. Set
`screen_priority_flight` or `screen_priority_iss` to override those values.

Future plugins should use bounded claims and check `can_render(owner)` again
while holding the display lock immediately before writing to the device.
