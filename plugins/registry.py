"""Deterministic lifecycle management for display plugins."""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Protocol, Sequence, runtime_checkable

from .override import DisplayOverride, OverrideCapability

logger = logging.getLogger(__name__)


@runtime_checkable
class DisplayPlugin(Protocol):
    """Minimal lifecycle contract implemented by first-class plugins."""

    name: str

    def start(self) -> None:
        """Start background work."""

    def stop(self) -> None:
        """Stop background work."""

    @property
    def override_capabilities(self) -> Sequence[OverrideCapability]:
        """Return the claims this plugin may make."""

    @property
    def display_overrides(self) -> Sequence[DisplayOverride]:
        """Return forced-display API capabilities."""


class PluginRegistry:
    """Register and run plugins in stable registration order."""

    def __init__(self, plugins: Iterable[DisplayPlugin] = ()):
        self._plugins: List[DisplayPlugin] = []
        self._names = set()
        self._started: List[DisplayPlugin] = []
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: DisplayPlugin) -> DisplayPlugin:
        name = getattr(plugin, "name", "")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("plugin name must not be empty")
        name = name.strip()
        if name in self._names:
            raise ValueError(f"duplicate plugin name: {name}")
        if any(existing is plugin for existing in self._plugins):
            raise ValueError(f"plugin instance is already registered: {name}")
        self._names.add(name)
        self._plugins.append(plugin)
        return plugin

    @property
    def plugins(self) -> tuple:
        return tuple(self._plugins)

    def get(self, name: str) -> DisplayPlugin:
        for plugin in self._plugins:
            if plugin.name.strip() == name.strip():
                return plugin
        raise KeyError(name)

    @property
    def display_overrides(self) -> tuple:
        overrides = []
        accepted: Dict[str, str] = {}
        for plugin in self._plugins:
            for override in getattr(plugin, "display_overrides", ()):
                for name in override.accepted_names:
                    existing = accepted.get(name)
                    if existing is not None:
                        raise ValueError(
                            f"display override name {name!r} is already used by {existing!r}"
                        )
                    accepted[name] = override.module
                overrides.append(override)
        return tuple(overrides)

    def start_all(self) -> None:
        """Start every unstarted plugin, isolating failures between plugins."""

        started_ids = {id(plugin) for plugin in self._started}
        for plugin in self._plugins:
            if id(plugin) in started_ids:
                continue
            try:
                plugin.start()
            except Exception:
                logger.exception("Failed to start plugin %s", plugin.name)
                try:
                    plugin.stop()
                except Exception:
                    logger.exception(
                        "Failed to clean up plugin %s after start failure",
                        plugin.name,
                    )
                continue
            self._started.append(plugin)
            started_ids.add(id(plugin))

    def stop_all(self) -> None:
        """Stop successfully started plugins in reverse order."""

        for plugin in reversed(tuple(self._started)):
            try:
                plugin.stop()
            except Exception:
                logger.exception("Failed to stop plugin %s", plugin.name)
                continue
            self._started.remove(plugin)

    start = start_all
    stop = stop_all
