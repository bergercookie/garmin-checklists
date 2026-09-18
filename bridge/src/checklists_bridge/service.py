"""Application logic: the only module the web layer talks to.

It owns the three things that are actually interesting:
  * provider configuration and the onboarding selection,
  * refreshing the snapshot the watch reads,
  * editing local checklists.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from typing import Any

from checklists_bridge.models import Checklist, SourceRef, qualify, unqualify
from checklists_bridge.providers import REGISTRY, ProviderError, ProviderSpec, TaskProvider
from checklists_bridge.providers.local import LocalProvider
from checklists_bridge.providers.registry import ProviderRegistry
from checklists_bridge.security import new_device_token
from checklists_bridge.storage import Database, State

LOGGER = logging.getLogger(__name__)


class NotFoundError(Exception):
    """The requested checklist or provider does not exist."""


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    """What the web UI shows for one provider."""

    spec: ProviderSpec
    configured: bool
    selected: tuple[str, ...]
    #: Config with secret fields blanked out, safe to send to the browser.
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RefreshReport:
    """Outcome of pulling every selected source from every provider."""

    checklists: tuple[Checklist, ...]
    errors: tuple[str, ...] = ()
    at: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class SyncHealth:
    """Whether the watch is looking at fresh data or at a frozen copy."""

    #: Last refresh that completed with no errors.
    synced_at: int
    #: Last refresh attempted at all.
    attempted_at: int
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


class _DatabaseLocalStore:
    """Adapts :class:`Database` to the local provider's tiny store protocol."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def load(self) -> list[Checklist]:
        return list(self._database.read().local_checklists)

    @contextmanager
    def mutate(self) -> Iterator[list[Checklist]]:
        """Hold the database lock for the whole read-modify-write."""
        with self._database.update() as state:
            yield state.local_checklists


class ChecklistService:
    def __init__(self, database: Database, registry: ProviderRegistry | None = None) -> None:
        self._database = database
        self._registry = registry or REGISTRY
        self._local_store = _DatabaseLocalStore(database)

    @property
    def device_token(self) -> str:
        return self._database.read().device_token

    @property
    def session_secret(self) -> str:
        return self._database.read().session_secret

    @property
    def session_epoch(self) -> int:
        return self._database.read().session_epoch

    def revoke_sessions(self) -> None:
        """Sign every browser out, including this one.

        There is no per-device sign-out to offer instead: the cookie proves only
        that somebody knew the password, and nothing distinguishes one browser's
        from another's. This is the blunt instrument for a lost device or a
        password you have just changed.
        """
        with self._database.update() as state:
            state.session_epoch += 1

    def rotate_device_token(self) -> str:
        with self._database.update() as state:
            state.device_token = new_device_token()
            return state.device_token

    def provider_statuses(self) -> list[ProviderStatus]:
        state = self._database.read()
        statuses = []
        for spec in self._registry.all():
            saved = state.providers.get(spec.id)
            config = dict(saved.config) if saved else {}
            statuses.append(
                ProviderStatus(
                    spec=spec,
                    configured=spec.editable or self._is_configured(spec, config),
                    selected=tuple(saved.selection) if saved else (),
                    config=_redact(spec, config),
                )
            )
        return statuses

    def configure_provider(self, provider_id: str, config: dict[str, Any]) -> list[SourceRef]:
        """Save credentials after proving they work, and return what can be imported."""
        spec = self._spec(provider_id)
        merged = self._merge_secrets(spec, config)
        with closing(self._build(spec, merged)) as provider:
            sources = provider.list_sources()
        with self._database.update() as state:
            state.provider(provider_id).config = merged
        return sources

    def forget_provider(self, provider_id: str) -> None:
        """Drop a provider's credentials, selection and checklists."""
        self._spec(provider_id)
        with self._database.update() as state:
            state.providers.pop(provider_id, None)
            state.snapshot = [
                item for item in state.snapshot if unqualify(item.id).provider_id != provider_id
            ]

    def list_sources(self, provider_id: str) -> list[SourceRef]:
        with closing(self._provider(provider_id)) as provider:
            return provider.list_sources()

    def set_selection(self, provider_id: str, source_ids: Sequence[str]) -> None:
        """Record which sources the user picked during onboarding."""
        self._spec(provider_id)
        wanted = [str(item) for item in source_ids]
        with self._database.update() as state:
            state.provider(provider_id).selection = wanted
            keep = {qualify(provider_id, item) for item in wanted}
            state.snapshot = [
                item
                for item in state.snapshot
                if unqualify(item.id).provider_id != provider_id or item.id in keep
            ]

    # ------------------------------------------------------- local checklists

    def create_local_checklist(self, name: str) -> SourceRef:
        source = self._local().create_checklist(name)
        self._select_local(add=source.id)
        return source

    def rename_local_checklist(self, source_id: str, name: str) -> SourceRef:
        return self._local().rename_checklist(source_id, name)

    def delete_local_checklist(self, source_id: str) -> None:
        self._local().delete_checklist(source_id)
        self._select_local(remove=source_id)

    def set_local_items(self, source_id: str, items: Sequence[str]) -> Checklist:
        return self._local().set_items(source_id, items)

    def local_checklists(self) -> list[Checklist]:
        return self._local_store.load()

    # ------------------------------------------------------------------ sync

    def refresh(self) -> RefreshReport:
        """Re-read every selected source and replace the watch-facing snapshot."""
        state = self._database.read()
        previous = {item.id: item for item in state.snapshot}
        checklists: list[Checklist] = []
        errors: list[str] = []

        for provider_id, provider_state in sorted(state.providers.items()):
            if not provider_state.selection:
                continue
            try:
                provider = self._provider(provider_id)
            except ProviderError as error:
                errors.append(f"{provider_id}: {error}")
                checklists.extend(
                    previous[qualify(provider_id, source_id)]
                    for source_id in provider_state.selection
                    if qualify(provider_id, source_id) in previous
                )
                continue
            with closing(provider):
                for source_id in provider_state.selection:
                    checklist_id = qualify(provider_id, source_id)
                    try:
                        fetched = provider.fetch(source_id)
                    except ProviderError as error:
                        errors.append(f"{provider_id}/{source_id}: {error}")
                        if checklist_id in previous:
                            checklists.append(previous[checklist_id])
                        continue
                    checklists.append(
                        Checklist(id=checklist_id, name=fetched.name, items=fetched.items)
                    )

        now = int(time.time())
        for message in errors:
            # Without this the only record of a dead provider is the HTTP
            # response to a refresh the user did not ask for.
            LOGGER.warning("refresh failed for %s", message)

        with self._database.update() as fresh:
            fresh.snapshot = checklists
            fresh.last_attempt_at = now
            fresh.last_errors = list(errors)
            if not errors:
                fresh.snapshot_at = now
        return RefreshReport(checklists=tuple(checklists), errors=tuple(errors), at=now)

    def snapshot(self) -> tuple[list[Checklist], int]:
        """The watch-facing checklists and when that snapshot was taken."""
        state = self._database.read()
        return list(state.snapshot), state.snapshot_at

    def sync_health(self) -> SyncHealth:
        """How the last refresh went, for the UI to show rather than hide."""
        state = self._database.read()
        return SyncHealth(
            synced_at=state.snapshot_at,
            attempted_at=state.last_attempt_at,
            errors=tuple(state.last_errors),
        )

    def snapshot_checklist(self, checklist_id: str) -> Checklist:
        for item in self._database.read().snapshot:
            if item.id == checklist_id:
                return item
        raise NotFoundError(f"no checklist {checklist_id!r} in the current snapshot")

    # --------------------------------------------------------------- internals

    def _spec(self, provider_id: str) -> ProviderSpec:
        return self._registry.get(provider_id)

    def _provider(self, provider_id: str) -> TaskProvider:
        spec = self._spec(provider_id)
        saved = self._database.read().providers.get(provider_id)
        return self._build(spec, dict(saved.config) if saved else {})

    def _build(self, spec: ProviderSpec, config: dict[str, Any]) -> TaskProvider:
        # The local provider is the one provider whose data the bridge itself
        # owns, so it needs a store handed to it at build time.
        if spec.editable:
            config = {**config, "store": self._local_store}
        return spec.build(config)

    def _local(self) -> LocalProvider:
        provider = self._provider(LocalProvider.id)
        assert isinstance(provider, LocalProvider)
        return provider

    def _select_local(self, *, add: str | None = None, remove: str | None = None) -> None:
        with self._database.update() as state:
            selection = state.provider(LocalProvider.id).selection
            if add is not None and add not in selection:
                selection.append(add)
            if remove is not None and remove in selection:
                selection.remove(remove)

    def _is_configured(self, spec: ProviderSpec, config: dict[str, Any]) -> bool:
        return all(not item.required or config.get(item.name) for item in spec.config_fields)

    def _merge_secrets(self, spec: ProviderSpec, config: dict[str, Any]) -> dict[str, Any]:
        """Keep the stored secret when the UI submits the redacted placeholder.

        Only declared fields survive. The mapping goes on to be handed to the
        provider's constructor, so an undeclared key is an injection point into
        it -- posting ``client`` once replaced the provider's HTTP client with a
        string and turned every later request into a 500.
        """
        state: State = self._database.read()
        saved = state.providers.get(spec.id)
        declared = {item.name for item in spec.config_fields}
        merged = {key: value for key, value in config.items() if key in declared}
        for item in spec.config_fields:
            keep_saved = (
                item.kind == "password"
                and merged.get(item.name) in (None, "", REDACTED)
                and saved is not None
                and saved.config.get(item.name)
            )
            if keep_saved and saved is not None:
                merged[item.name] = saved.config[item.name]
        return merged


REDACTED = "********"


def _redact(spec: ProviderSpec, config: dict[str, Any]) -> dict[str, Any]:
    safe = dict(config)
    for item in spec.config_fields:
        if item.kind == "password" and safe.get(item.name):
            safe[item.name] = REDACTED
    return safe
