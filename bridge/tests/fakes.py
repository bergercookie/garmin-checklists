"""A provider that lives entirely in memory, for service and API tests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

from checklists_bridge.models import Checklist, SourceRef
from checklists_bridge.providers.base import (
    ProviderAuthError,
    SourceNotFoundError,
    TaskProvider,
)
from checklists_bridge.providers.registry import ConfigField, ProviderSpec

#: Shared between the factory and the tests, so a test can rewrite the fixture
#: data after the service has already built the provider.
CONTENT: dict[str, list[str]] = {}
NAMES: dict[str, str] = {}
FAIL: dict[str, bool] = {"auth": False}


class FakeProvider(TaskProvider):
    id: ClassVar[str] = "fake"
    label: ClassVar[str] = "Fake"

    def __init__(self, token: str) -> None:
        self._token = token

    def list_sources(self) -> list[SourceRef]:
        self._check()
        return [SourceRef(id=key, name=NAMES[key], item_count=len(CONTENT[key])) for key in CONTENT]

    def fetch(self, source_id: str) -> Checklist:
        self._check()
        if source_id not in CONTENT:
            raise SourceNotFoundError(source_id)
        return Checklist(id=source_id, name=NAMES[source_id], items=tuple(CONTENT[source_id]))

    def _check(self) -> None:
        if FAIL["auth"]:
            raise ProviderAuthError("fake provider says no")


def reset(sources: Mapping[str, tuple[str, list[str]]] | None = None) -> None:
    CONTENT.clear()
    NAMES.clear()
    FAIL["auth"] = False
    for key, (name, items) in (sources or {}).items():
        NAMES[key] = name
        CONTENT[key] = list(items)


def _factory(config: Mapping[str, Any]) -> FakeProvider:
    return FakeProvider(str(config["token"]))


SPEC = ProviderSpec(
    id=FakeProvider.id,
    label=FakeProvider.label,
    description="In-memory provider used by the test suite.",
    factory=_factory,
    config_fields=(ConfigField(name="token", label="Token", kind="password"),),
)
