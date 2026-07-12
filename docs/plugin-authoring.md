# Display plugin authoring

Plugins receive an immutable `PluginContext`, expose a stable `name`, and
implement idempotent `start()` and `stop()`. `PluginRegistry` starts them in
order, stops them in reverse, rejects duplicate names and override aliases, and
isolates lifecycle failures.

Temporary displays claim `ScreenArbiter`, acquire the context display lock, and
recheck ownership before drawing. `PeriodicRotatingScreen` provides this for
fixed sequences. View duration starts only after the claim wins the screen.
