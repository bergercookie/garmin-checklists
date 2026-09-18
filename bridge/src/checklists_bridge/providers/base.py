"""The provider contract every task backend implements.

Adding a backend means writing one class here (plus a registry entry) -- no other
layer of the bridge needs to change.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from typing import ClassVar
from urllib.parse import urlsplit

from checklists_bridge.models import Checklist, SourceRef


class ProviderError(Exception):
    """Base class for anything a provider can fail with."""


class ProviderAuthError(ProviderError):
    """Credentials were rejected by the upstream service."""


class ProviderUnavailableError(ProviderError):
    """Upstream service could not be reached or returned an unusable answer."""


class SourceNotFoundError(ProviderError):
    """The requested source does not exist (any more) in the provider."""


def checked_base_url(base_url: str, *, service: str, example: str) -> str:
    """Reject anything that is not an http(s) URL, with a message worth reading.

    Deliberately *not* a check that the host is public: a self-hosted instance on
    a private address is the normal case here, so blocking those would break the
    main use of the bridge. This only stops schemes that were never meant to be
    fetched, and the empty-host typos that otherwise surface as a puzzling
    connection error.
    """
    cleaned = base_url.strip().rstrip("/")
    parts = urlsplit(cleaned)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ProviderError(
            f"{base_url!r} is not a usable {service} URL: it needs to look like {example}"
        )
    return cleaned


class TaskProvider(abc.ABC):
    """Read-only view of an upstream task service.

    Providers are stateless with respect to tick state: the bridge never writes
    completion back upstream, so there is no ``set_done`` in this interface.
    """

    id: ClassVar[str]
    label: ClassVar[str]

    @abc.abstractmethod
    def list_sources(self) -> list[SourceRef]:
        """Return everything importable, for the onboarding picker."""

    @abc.abstractmethod
    def fetch(self, source_id: str) -> Checklist:
        """Return one source as a checklist. ``Checklist.id`` is the source id."""

    def close(self) -> None:  # noqa: B027  (concrete on purpose, see below)
        """Release anything held open. Safe to call more than once.

        Deliberately not abstract: a provider that holds nothing open -- the
        built-in local one, and any future provider backed by a file -- should
        not have to write an empty method to satisfy the interface.

        A provider is built fresh for every refresh, so one that opens a
        connection pool and never closes it leaks a handful of sockets per sync,
        for as long as the bridge runs.
        """


class EditableTaskProvider(TaskProvider):
    """A provider whose contents the bridge itself owns and may modify.

    Only the built-in local provider implements this; it is what powers the
    "no external vendor configured" case.
    """

    @abc.abstractmethod
    def create_checklist(self, name: str) -> SourceRef:
        """Create an empty checklist and return its reference."""

    @abc.abstractmethod
    def rename_checklist(self, source_id: str, name: str) -> SourceRef:
        """Rename an existing checklist."""

    @abc.abstractmethod
    def delete_checklist(self, source_id: str) -> None:
        """Remove a checklist entirely."""

    @abc.abstractmethod
    def set_items(self, source_id: str, items: Sequence[str]) -> Checklist:
        """Replace every item of a checklist.

        One whole-list write covers add, edit, delete and reorder, which keeps
        both this interface and the web UI small.
        """
