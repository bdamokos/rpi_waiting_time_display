"""First-class building blocks for optional display plugins."""

from .config import (
    ConfigError,
    env_bool,
    env_float,
    env_int,
    env_json,
    env_json_list,
    env_json_object,
    env_str,
)
from .context import PluginContext, normalize_plugin_context
from .override import DisplayOverride, OverrideCapability
from .registry import DisplayPlugin, PluginRegistry
from .rotating import PeriodicRotatingScreen, RotatingView

__all__ = [
    "ConfigError",
    "DisplayOverride",
    "DisplayPlugin",
    "OverrideCapability",
    "PeriodicRotatingScreen",
    "PluginContext",
    "PluginRegistry",
    "RotatingView",
    "env_bool",
    "env_float",
    "env_int",
    "env_json",
    "env_json_list",
    "env_json_object",
    "env_str",
    "normalize_plugin_context",
]
