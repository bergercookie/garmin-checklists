"""Provider catalogue: ids, human labels, config schema and factories.

The web UI renders provider setup forms straight from :class:`ConfigField`, so a
new provider becomes configurable without touching any HTML.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from checklists_bridge.providers.base import ProviderError, TaskProvider

ProviderFactory = Callable[[Mapping[str, Any]], TaskProvider]

#: How the web UI renders an input. The web UI branches on this, so a typo
#: here would silently produce a broken form; Literal makes it a type error.
FieldKind = Literal["text", "password", "url", "checkbox"]


class ConfigField(BaseModel):
    """One input on the provider setup form.

    A model rather than a dataclass so that ``model_dump`` is the single
    definition of what reaches the browser: adding an attribute here cannot be
    forgotten in a hand-written serialiser.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    label: str
    kind: FieldKind = "text"
    required: bool = True
    placeholder: str = ""
    help: str = ""
    default: Any = ""


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    """Everything the bridge knows about a provider before instantiating it."""

    id: str
    label: str
    description: str
    factory: ProviderFactory
    editable: bool = False
    config_fields: tuple[ConfigField, ...] = field(default_factory=tuple)

    def build(self, config: Mapping[str, Any]) -> TaskProvider:
        missing = [
            item.label for item in self.config_fields if item.required and not config.get(item.name)
        ]
        if missing:
            raise ProviderError(f"missing required setting(s): {', '.join(missing)}")
        return self.factory(config)

    def to_dict(self) -> dict[str, Any]:
        # dict[str, Any] rather than a tighter type deliberately: this is a
        # JSON-serialization boundary (handed straight to the browser), the
        # same reasoning behind Checklist.to_dict in models.py. ConfigField's
        # own fields are still precisely typed by pydantic; only the outer
        # shape, mixing them with str/bool, is loose.
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "editable": self.editable,
            "fields": [item.model_dump() for item in self.config_fields],
        }


class ProviderRegistry:
    """A mutable catalogue; the module-level :data:`REGISTRY` is the default one."""

    def __init__(self) -> None:
        self._specs: dict[str, ProviderSpec] = {}

    def register(self, spec: ProviderSpec) -> ProviderSpec:
        if spec.id in self._specs:
            raise ValueError(f"provider {spec.id!r} is already registered")
        self._specs[spec.id] = spec
        return spec

    def get(self, provider_id: str) -> ProviderSpec:
        try:
            return self._specs[provider_id]
        except KeyError:
            raise ProviderError(f"unknown provider: {provider_id!r}") from None

    def all(self) -> Iterable[ProviderSpec]:
        return tuple(self._specs.values())


REGISTRY = ProviderRegistry()
