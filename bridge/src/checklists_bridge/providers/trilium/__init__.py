"""Trilium Notes: a note is a checklist, its ``[]`` lines are the items.

Trilium has no concept of a task list, so the mapping is by convention:

    note tagged #checklist   ->  checklist
    line starting "[]"       ->  item
    line starting "[x]"      ->  ignored, never imported
    everything else          ->  ignored

Which notes are offered is a Trilium search expression, so the default
``#checklist`` can become ``#packing OR #dive`` or anything else the search
syntax accepts. See notes.py for the line syntax and docs/trilium.md for the
user-facing version.

Two ETAPI routes are used per sync and no others; see etapi.py.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, ClassVar

import httpx

from checklists_bridge.models import Checklist, SourceRef, clean_items, clean_name
from checklists_bridge.providers.base import (
    TaskProvider,
    checked_base_url,
)
from checklists_bridge.providers.registry import REGISTRY, ConfigField, ProviderSpec
from checklists_bridge.providers.trilium.etapi import Etapi
from checklists_bridge.providers.trilium.notes import checklist_items

LOGGER = logging.getLogger(__name__)

#: What the picker offers when nothing else is configured. A label, because
#: tagging a note is the one thing you can do from anywhere in Trilium.
DEFAULT_SEARCH = "#checklist"

#: Stop the picker growing without bound on a large instance. Hitting this is
#: reported rather than silently truncated.
MAX_NOTES = 200

#: Protected notes are encrypted at rest and their content is unreadable over
#: ETAPI; offering them would import empty checklists.
IMPORTABLE_TYPES = frozenset({"text", "code"})


class TriliumProvider(TaskProvider):
    id: ClassVar[str] = "trilium"
    label: ClassVar[str] = "Trilium Notes"

    def __init__(
        self,
        base_url: str,
        token: str,
        search: str = DEFAULT_SEARCH,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._search = search.strip() or DEFAULT_SEARCH
        self._api = Etapi(
            checked_base_url(base_url, service="Trilium", example="https://trilium.example.com"),
            token,
            client=client,
        )

    def close(self) -> None:
        self._api.close()

    def list_sources(self) -> list[SourceRef]:
        notes = self._api.search(self._search, limit=MAX_NOTES)
        if len(notes) >= MAX_NOTES:
            LOGGER.warning(
                "Trilium search %r returned at least %d notes; narrow it with a label",
                self._search,
                MAX_NOTES,
            )
        return [
            SourceRef(id=str(note["noteId"]), name=str(note.get("title", "")))
            for note in notes
            if self._is_importable(note)
        ]

    def fetch(self, source_id: str) -> Checklist:
        # The note is read directly rather than resolved from the search
        # results, so a checklist whose #checklist label was removed after it
        # was imported keeps its name and keeps working, instead of silently
        # becoming "Note abc123".
        note = self._api.note(source_id)
        return Checklist(
            id=str(source_id),
            name=clean_name(str(note.get("title") or f"Note {source_id}")),
            items=clean_items(checklist_items(self._api.content(source_id))),
        )

    @staticmethod
    def _is_importable(note: Mapping[str, Any]) -> bool:
        return (
            bool(note.get("noteId"))
            and not note.get("isProtected")
            and str(note.get("type", "text")) in IMPORTABLE_TYPES
        )


def _factory(config: Mapping[str, Any]) -> TriliumProvider:
    return TriliumProvider(
        base_url=str(config["base_url"]),
        token=str(config["token"]),
        search=str(config.get("search") or DEFAULT_SEARCH),
        client=config.get("client"),
    )


SPEC = REGISTRY.register(
    ProviderSpec(
        id=TriliumProvider.id,
        label=TriliumProvider.label,
        description="Import Trilium notes whose lines start with [] as checklists.",
        factory=_factory,
        config_fields=(
            ConfigField(
                name="base_url",
                label="Trilium URL",
                kind="url",
                placeholder="https://trilium.example.com",
                help="Root URL of your instance, without /etapi.",
            ),
            ConfigField(
                name="token",
                label="ETAPI token",
                kind="password",
                placeholder="",
                help="Trilium > Options > ETAPI > Create new token.",
            ),
            ConfigField(
                name="search",
                label="Which notes",
                required=False,
                default=DEFAULT_SEARCH,
                placeholder=DEFAULT_SEARCH,
                help="A Trilium search. The default offers every note labelled #checklist.",
            ),
        ),
    )
)
