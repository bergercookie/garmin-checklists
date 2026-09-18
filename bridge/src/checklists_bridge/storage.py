"""Persistence: one JSON file, written atomically.

A single file keeps the bridge trivial to back up, inspect and hand-edit, which
matters more here than query performance -- the data set is a handful of lists.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from checklists_bridge.models import Checklist
from checklists_bridge.security import new_device_token, new_secret

SCHEMA_VERSION = 1


class StorageError(Exception):
    """The data file could not be read. Always carries the path and a next step."""


#: The previous version, kept beside the current one.
BACKUP_SUFFIX = ".bak"

#: Owner-only. The file is a bag of secrets; the directory is created alongside.
FILE_MODE = 0o600
DIRECTORY_MODE = 0o700


@dataclass
class ProviderState:
    """Saved configuration for one provider (credentials, endpoint, options)."""

    config: dict[str, Any] = field(default_factory=dict)
    #: Provider-native source ids the user chose to import during onboarding.
    selection: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"config": self.config, "selection": self.selection}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProviderState:
        return cls(
            config=dict(raw.get("config", {})),
            selection=[str(item) for item in raw.get("selection", [])],
        )


@dataclass
class State:
    """The whole persisted document."""

    device_token: str = field(default_factory=new_device_token)
    session_secret: str = field(default_factory=new_secret)
    #: Bumped to sign every browser out at once. Cookies carry the generation
    #: they were issued under, so old ones stop verifying the moment this moves.
    session_epoch: int = 0
    providers: dict[str, ProviderState] = field(default_factory=dict)
    #: Flat list of checklists owned by the local provider.
    local_checklists: list[Checklist] = field(default_factory=list)
    #: Last successful fetch from the providers -- this is what the watch reads.
    snapshot: list[Checklist] = field(default_factory=list)
    #: When the snapshot was last refreshed with *no* errors. Deliberately not
    #: touched by a failed sync: a "last synced 2 minutes ago" that really means
    #: "last tried 2 minutes ago, and it failed" is how this rots quietly.
    snapshot_at: int = 0
    #: When a refresh was last attempted, successful or not.
    last_attempt_at: int = 0
    #: What went wrong on that attempt. Empty means it went cleanly.
    last_errors: list[str] = field(default_factory=list)

    def provider(self, provider_id: str) -> ProviderState:
        """Return (creating if needed) the state bucket for one provider."""
        return self.providers.setdefault(provider_id, ProviderState())

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "device_token": self.device_token,
            "session_secret": self.session_secret,
            "session_epoch": self.session_epoch,
            "providers": {key: value.to_dict() for key, value in self.providers.items()},
            "local_checklists": [item.to_dict() for item in self.local_checklists],
            "snapshot": [item.to_dict() for item in self.snapshot],
            "snapshot_at": self.snapshot_at,
            "last_attempt_at": self.last_attempt_at,
            "last_errors": list(self.last_errors),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> State:
        version = int(raw.get("version", SCHEMA_VERSION))
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"data file was written by a newer bridge (schema {version}); upgrade first"
            )
        state = cls(
            device_token=str(raw.get("device_token") or new_device_token()),
            session_secret=str(raw.get("session_secret") or new_secret()),
            session_epoch=int(raw.get("session_epoch", 0)),
            providers={
                key: ProviderState.from_dict(value)
                for key, value in raw.get("providers", {}).items()
            },
            local_checklists=[
                Checklist.from_dict(item) for item in raw.get("local_checklists", [])
            ],
            snapshot=[Checklist.from_dict(item) for item in raw.get("snapshot", [])],
            snapshot_at=int(raw.get("snapshot_at", 0)),
            last_attempt_at=int(raw.get("last_attempt_at", 0)),
            last_errors=[str(item) for item in raw.get("last_errors", [])],
        )
        return state


class Database:
    """Thread-safe read/modify/write access to the JSON state file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> State:
        with self._lock:
            return self._read_unlocked()

    @contextmanager
    def update(self) -> Iterator[State]:
        """Yield the state under the lock and write it back when the block ends.

        A block that raises writes nothing, which is the point: a half-applied
        change is worse than none.
        """
        with self._lock:
            state = self._read_unlocked()
            yield state
            self._write_unlocked(state)

    def _read_unlocked(self) -> State:
        if not self._path.exists():
            state = State()
            self._write_unlocked(state)
            return state
        raw, state = self._parse(self._path.read_text(encoding="utf-8"))
        # `from_dict` mints a replacement for a missing or blanked credential.
        # Writing it back at once is what makes blanking `session_secret` by hand
        # a working "sign everybody out" -- without this it would mint a *new*
        # secret on every read, so the cookie handed out by one request could
        # never be verified by the next, and nobody could sign in again either.
        if (state.session_secret, state.device_token) != (
            raw.get("session_secret"),
            raw.get("device_token"),
        ):
            self._write_unlocked(state)
        return state

    def _parse(self, text: str) -> tuple[dict[str, Any], State]:
        """Turn the file's text into a State, or say clearly why it cannot.

        Returns the raw mapping too, so the caller can tell which fields were
        absent. The file is documented as hand-editable, so a stray comma is a
        thing that will happen; without this it surfaces as a 500 on every
        endpoint, with a JSONDecodeError that never mentions which file.
        """
        try:
            raw = json.loads(text)
            return raw, State.from_dict(raw)
        except json.JSONDecodeError as error:
            raise StorageError(
                f"{self._path} is not valid JSON ({error}). "
                f"Restore {self._path.name}{BACKUP_SUFFIX} or the last backup you took."
            ) from error
        except (TypeError, ValueError, KeyError) as error:
            raise StorageError(
                f"{self._path} is not a valid bridge data file ({error!r}). "
                f"Restore {self._path.name}{BACKUP_SUFFIX} or the last backup you took."
            ) from error

    def _write_unlocked(self, state: State) -> None:
        # The file holds provider API tokens, the session signing secret and the
        # device token in clear, so it should never be readable by other accounts
        # on the machine -- which matters most for the bind-mount setup, where it
        # lands in a directory on the host.
        self._path.parent.mkdir(parents=True, exist_ok=True, mode=DIRECTORY_MODE)
        # The pid is in the name so that a second process -- which this file is
        # not designed to tolerate, but which happens by accident -- cannot
        # publish another's half-written temporary file through the rename below.
        temporary = self._path.with_suffix(f"{self._path.suffix}.{os.getpid()}.tmp")
        # Opened restricted rather than chmod-ed afterwards: a window in which the
        # secrets are world-readable is still a window.
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, FILE_MODE)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n")
                # The rename below is atomic against a concurrent reader, but on
                # its own it is not durable: after a power cut the directory entry
                # can point at a file whose contents never reached the disk.
                handle.flush()
                os.fsync(handle.fileno())
            # One generation of history, so a bad write or a bad hand-edit is
            # recoverable without reaching for last night's backup.
            if self._path.exists():
                self._path.replace(self._path.with_name(self._path.name + BACKUP_SUFFIX))
            temporary.replace(self._path)
            self._sync_directory()
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def _sync_directory(self) -> None:
        """Persist the rename itself, not just the bytes it points at."""
        descriptor = os.open(self._path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
