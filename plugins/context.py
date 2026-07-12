"""Shared services supplied to display plugins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from screen_arbiter import ScreenArbiter


@dataclass(frozen=True)
class PluginContext:
    """Immutable references to the application's shared display services."""

    epd: Any
    arbiter: ScreenArbiter
    display_lock: Any
    on_render: Optional[Callable[[str], None]] = None


def normalize_plugin_context(
    epd: Any,
    arbiter: Optional[ScreenArbiter],
    display_lock: Any,
    on_render: Optional[Callable[[str], None]],
) -> PluginContext:
    """Accept either a plugin context or the legacy constructor arguments."""

    if isinstance(epd, PluginContext):
        if arbiter is not None or display_lock is not None:
            raise TypeError("arbiter and display_lock are supplied by PluginContext")
        return epd
    if arbiter is None or display_lock is None:
        raise TypeError("epd, arbiter, and display_lock are required")
    return PluginContext(epd, arbiter, display_lock, on_render)
