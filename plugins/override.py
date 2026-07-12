"""Metadata describing plugin claims and forced display overrides."""

from dataclasses import dataclass
from typing import Callable, Tuple

DisplayOverrideRenderer = Callable[[str, Callable[[], bool]], bool]


@dataclass(frozen=True)
class OverrideCapability:
    """A screen claim a plugin may make at runtime."""

    owner: str
    priority: int
    exclusive: bool = False
    description: str = ""

    def __post_init__(self):
        if not self.owner.strip():
            raise ValueError("override capability owner must not be empty")
        object.__setattr__(self, "owner", self.owner.strip())
        object.__setattr__(self, "priority", int(self.priority))


@dataclass(frozen=True)
class DisplayOverride:
    """A canonical forced-display module and its accepted aliases."""

    module: str
    render: DisplayOverrideRenderer
    aliases: Tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self):
        module = self.module.strip().lower()
        if not module:
            raise ValueError("display override module must not be empty")
        aliases = tuple(alias.strip().lower() for alias in self.aliases)
        if any(not alias for alias in aliases):
            raise ValueError("display override aliases must not be empty")
        if len(set(aliases)) != len(aliases):
            raise ValueError(f"duplicate aliases for display override: {module}")
        object.__setattr__(self, "module", module)
        object.__setattr__(self, "aliases", aliases)

    @property
    def accepted_names(self) -> Tuple[str, ...]:
        return (self.module,) + self.aliases
