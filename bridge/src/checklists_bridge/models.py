"""Domain types shared by every layer of the bridge.

The bridge only ever moves *item names* around.  Tick state lives exclusively on
the watch and is wiped on every sync, so nothing here records completion.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, NamedTuple

#: Separator between a provider id and a provider-native source id.
QUALIFIER = ":"

#: Guard rails so a runaway project cannot blow up the watch's memory.
MAX_ITEMS_PER_CHECKLIST = 100
MAX_ITEM_LENGTH = 64
MAX_NAME_LENGTH = 32


class DomainError(Exception):
    """Raised when caller-supplied data is not valid."""


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Something in a provider that *could* be imported as a checklist.

    For Vikunja a source is a project; for the local provider it is a checklist
    the user typed in by hand.
    """

    id: str
    name: str
    item_count: int | None = None


@dataclass(frozen=True, slots=True)
class Checklist:
    """A named, ordered list of item labels."""

    id: str
    name: str
    items: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "items": list(self.items)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Checklist:
        return cls(
            id=str(raw["id"]),
            name=str(raw["name"]),
            items=tuple(str(item) for item in raw.get("items", ())),
        )


def qualify(provider_id: str, source_id: str) -> str:
    """Build the globally unique checklist id the watch sees (``vikunja:12``)."""
    if QUALIFIER in provider_id:
        raise DomainError(f"provider id must not contain {QUALIFIER!r}: {provider_id!r}")
    return f"{provider_id}{QUALIFIER}{source_id}"


class Qualified(NamedTuple):
    """The two halves of a qualified checklist id, e.g. ``vikunja:12``.

    A ``NamedTuple`` rather than a bare ``tuple[str, str]`` so a call site can
    write ``.provider_id`` instead of ``[0]``; it is still a plain tuple, so
    indexing and equality against ``("vikunja", "12")`` keep working too.
    """

    provider_id: str
    source_id: str


def unqualify(checklist_id: str) -> Qualified:
    """Split a qualified checklist id back into ``(provider_id, source_id)``."""
    provider_id, separator, source_id = checklist_id.partition(QUALIFIER)
    if not separator or not provider_id or not source_id:
        raise DomainError(f"malformed checklist id: {checklist_id!r}")
    return Qualified(provider_id, source_id)


def clean_name(name: str) -> str:
    """Normalise a checklist name, rejecting empty ones."""
    cleaned = " ".join(name.split())[:MAX_NAME_LENGTH]
    if not cleaned:
        raise DomainError("checklist name must not be empty")
    return cleaned


def clean_items(items: object) -> tuple[str, ...]:
    """Normalise item labels: trim, drop blanks, truncate, cap the count."""
    if isinstance(items, str) or not isinstance(items, Iterable):
        raise DomainError("items must be a list of strings")
    cleaned = []
    for item in items:
        label = " ".join(str(item).split())[:MAX_ITEM_LENGTH]
        if label:
            cleaned.append(label)
    return tuple(cleaned[:MAX_ITEMS_PER_CHECKLIST])
