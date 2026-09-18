from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest

from checklists_bridge.models import Checklist, DomainError
from checklists_bridge.providers.base import SourceNotFoundError
from checklists_bridge.providers.local import LocalProvider


class MemoryStore:
    def __init__(self) -> None:
        self.checklists: list[Checklist] = []

    def load(self) -> list[Checklist]:
        return list(self.checklists)

    @contextmanager
    def mutate(self) -> Iterator[list[Checklist]]:
        # A copy in, the copy back out: a real store yields the live list under a
        # lock, and a fake that aliased `self.checklists` would hide a provider
        # that forgot to write its changes back.
        working = list(self.checklists)
        yield working
        self.checklists = working


@pytest.fixture
def provider() -> LocalProvider:
    return LocalProvider(MemoryStore())


def test_create_then_list(provider: LocalProvider) -> None:
    created = provider.create_checklist("  Dive  kit ")
    assert created.name == "Dive kit"
    assert [source.id for source in provider.list_sources()] == [created.id]


def test_set_items_replaces_the_whole_list(provider: LocalProvider) -> None:
    created = provider.create_checklist("Kit")
    provider.set_items(created.id, ["Mask", "Fins"])
    assert provider.fetch(created.id).items == ("Mask", "Fins")
    provider.set_items(created.id, ["Torch"])
    assert provider.fetch(created.id).items == ("Torch",)


def test_set_items_cleans_input(provider: LocalProvider) -> None:
    created = provider.create_checklist("Kit")
    checklist = provider.set_items(created.id, ["  Mask ", "", "Fins"])
    assert checklist.items == ("Mask", "Fins")


def test_rename(provider: LocalProvider) -> None:
    created = provider.create_checklist("Kit")
    provider.set_items(created.id, ["Mask"])
    renamed = provider.rename_checklist(created.id, "Dive kit")
    assert renamed.name == "Dive kit"
    assert provider.fetch(created.id).items == ("Mask",)


def test_delete(provider: LocalProvider) -> None:
    created = provider.create_checklist("Kit")
    provider.delete_checklist(created.id)
    assert provider.list_sources() == []
    with pytest.raises(SourceNotFoundError):
        provider.fetch(created.id)


@pytest.mark.parametrize(
    "action",
    [
        lambda provider: provider.fetch("nope"),
        lambda provider: provider.delete_checklist("nope"),
        lambda provider: provider.rename_checklist("nope", "x"),
        lambda provider: provider.set_items("nope", []),
    ],
)
def test_unknown_ids_raise(
    provider: LocalProvider, action: Callable[[LocalProvider], object]
) -> None:
    with pytest.raises(SourceNotFoundError):
        action(provider)


def test_blank_names_are_rejected(provider: LocalProvider) -> None:
    with pytest.raises(DomainError):
        provider.create_checklist("   ")


def test_editing_the_second_checklist_leaves_the_first_alone(provider: LocalProvider) -> None:
    first = provider.create_checklist("Kit")
    second = provider.create_checklist("Travel")
    provider.set_items(first.id, ["Mask"])

    provider.set_items(second.id, ["Passport"])

    assert provider.fetch(first.id).items == ("Mask",)
    assert provider.fetch(second.id).items == ("Passport",)
