"""The built-in provider: checklists typed in through the web UI, stored by the bridge.

This is what makes the app useful with no third-party account at all.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, ClassVar, Protocol

from checklists_bridge.models import Checklist, SourceRef, clean_items, clean_name
from checklists_bridge.providers.base import EditableTaskProvider, SourceNotFoundError
from checklists_bridge.providers.registry import REGISTRY, ProviderSpec


class LocalChecklistStore(Protocol):
    """Persistence seam so this module never imports the storage layer."""

    def load(self) -> list[Checklist]: ...

    def mutate(self) -> AbstractContextManager[list[Checklist]]:
        """Yield the stored list for editing in place, exclusively.

        Every write goes through this rather than load-then-save: two devices
        adding a checklist at the same moment would otherwise each read the old
        list and write it back, and whichever finished second would silently
        erase the other's.
        """
        ...


class LocalProvider(EditableTaskProvider):
    id: ClassVar[str] = "local"
    label: ClassVar[str] = "On this bridge"

    def __init__(self, store: LocalChecklistStore) -> None:
        self._store = store

    def list_sources(self) -> list[SourceRef]:
        return [
            SourceRef(id=item.id, name=item.name, item_count=len(item.items))
            for item in self._store.load()
        ]

    def fetch(self, source_id: str) -> Checklist:
        for item in self._store.load():
            if item.id == source_id:
                return item
        raise SourceNotFoundError(f"no local checklist with id {source_id!r}")

    def create_checklist(self, name: str) -> SourceRef:
        checklist = Checklist(id=uuid.uuid4().hex[:8], name=clean_name(name), items=())
        with self._store.mutate() as checklists:
            checklists.append(checklist)
        return SourceRef(id=checklist.id, name=checklist.name, item_count=0)

    def rename_checklist(self, source_id: str, name: str) -> SourceRef:
        updated = self._replace(source_id, name=clean_name(name))
        return SourceRef(id=updated.id, name=updated.name, item_count=len(updated.items))

    def delete_checklist(self, source_id: str) -> None:
        with self._store.mutate() as checklists:
            remaining = [item for item in checklists if item.id != source_id]
            if len(remaining) == len(checklists):
                raise SourceNotFoundError(f"no local checklist with id {source_id!r}")
            checklists[:] = remaining

    def set_items(self, source_id: str, items: Sequence[str]) -> Checklist:
        return self._replace(source_id, items=clean_items(items))

    def _replace(
        self, source_id: str, *, name: str | None = None, items: tuple[str, ...] | None = None
    ) -> Checklist:
        with self._store.mutate() as checklists:
            for index, item in enumerate(checklists):
                if item.id != source_id:
                    continue
                updated = Checklist(
                    id=item.id,
                    name=item.name if name is None else name,
                    items=item.items if items is None else items,
                )
                checklists[index] = updated
                return updated
            raise SourceNotFoundError(f"no local checklist with id {source_id!r}")


def _factory(config: Mapping[str, Any]) -> LocalProvider:
    store = config["store"]
    return LocalProvider(store)


SPEC = REGISTRY.register(
    ProviderSpec(
        id=LocalProvider.id,
        label=LocalProvider.label,
        description="Checklists you type in here. No external account needed.",
        factory=_factory,
        editable=True,
        config_fields=(),
    )
)
