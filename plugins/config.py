"""Strict, reusable environment configuration helpers for plugins."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Mapping, Optional, TypeVar

T = TypeVar("T")
_MISSING = object()


class ConfigError(ValueError):
    """Raised when a configured plugin value cannot be parsed."""


def _value(name: str, default: Any, environ: Optional[Mapping[str, str]]) -> Any:
    source = os.environ if environ is None else environ
    value = source.get(name, _MISSING)
    if value is _MISSING or value is None or not str(value).strip():
        if default is _MISSING:
            raise ConfigError(f"missing required environment variable {name}")
        return default
    return value


def env_str(
    name: str,
    default: Any = _MISSING,
    *,
    environ: Optional[Mapping[str, str]] = None,
    strip: bool = True,
) -> str:
    value = str(_value(name, default, environ))
    return value.strip() if strip else value


def env_bool(
    name: str,
    default: Any = _MISSING,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> bool:
    value = _value(name, default, environ)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be a boolean, got {value!r}")


def _number(
    name: str,
    parser: Callable[[Any], T],
    kind: str,
    default: Any,
    environ: Optional[Mapping[str, str]],
    minimum: Optional[T],
    maximum: Optional[T],
) -> T:
    value = _value(name, default, environ)
    try:
        parsed = parser(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{name} must be {kind}, got {value!r}") from exc
    if minimum is not None and parsed < minimum:
        raise ConfigError(f"{name} must be at least {minimum}, got {parsed}")
    if maximum is not None and parsed > maximum:
        raise ConfigError(f"{name} must be at most {maximum}, got {parsed}")
    return parsed


def env_int(
    name: str,
    default: Any = _MISSING,
    *,
    environ: Optional[Mapping[str, str]] = None,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    return _number(name, int, "an integer", default, environ, minimum, maximum)


def env_float(
    name: str,
    default: Any = _MISSING,
    *,
    environ: Optional[Mapping[str, str]] = None,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    return _number(name, float, "a number", default, environ, minimum, maximum)


def env_json(
    name: str,
    default: Any = _MISSING,
    *,
    environ: Optional[Mapping[str, str]] = None,
    expected_type: Optional[type] = None,
) -> Any:
    value = _value(name, default, environ)
    if not isinstance(value, str):
        parsed = value
    else:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"{name} must contain valid JSON: {exc.msg} at position {exc.pos}"
            ) from exc
    if expected_type is not None and not isinstance(parsed, expected_type):
        raise ConfigError(
            f"{name} must contain a JSON {expected_type.__name__}, "
            f"got {type(parsed).__name__}"
        )
    return parsed


def env_json_object(
    name: str,
    default: Any = _MISSING,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> dict:
    return env_json(name, default, environ=environ, expected_type=dict)


def env_json_list(
    name: str,
    default: Any = _MISSING,
    *,
    environ: Optional[Mapping[str, str]] = None,
) -> list:
    return env_json(name, default, environ=environ, expected_type=list)
