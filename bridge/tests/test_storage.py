from __future__ import annotations

import json
import stat
from pathlib import Path
from typing import Any

import pytest

from checklists_bridge.models import Checklist
from checklists_bridge.storage import Database, State, StorageError


def test_first_read_creates_the_file_with_a_token(tmp_path: Path) -> None:
    database = Database(tmp_path / "nested" / "bridge.json")
    state = database.read()
    assert database.path.exists()
    assert state.device_token


def test_update_persists_and_leaves_no_temp_file(database: Database) -> None:
    with database.update() as state:
        state.provider("vikunja").selection = ["12"]
        state.local_checklists = [Checklist(id="a", name="Kit", items=("Mask",))]

    reloaded = database.read()
    assert reloaded.providers["vikunja"].selection == ["12"]
    assert reloaded.local_checklists[0].items == ("Mask",)
    assert list(database.path.parent.glob("*.tmp")) == []


def test_tokens_are_stable_across_reads(database: Database) -> None:
    assert database.read().device_token == database.read().device_token


def test_newer_schema_is_refused() -> None:
    with pytest.raises(ValueError, match="newer bridge"):
        State.from_dict({"version": 99})


def test_file_is_human_readable(database: Database) -> None:
    database.read()
    payload = json.loads(database.path.read_text())
    assert payload["version"] == 1
    assert "device_token" in payload


def test_the_file_of_secrets_is_readable_only_by_its_owner(tmp_path: Path) -> None:
    # It holds the Vikunja token, the session signing secret and the device
    # token in clear, and with a bind mount it lands in a directory on the host.
    database = Database(tmp_path / "nested" / "bridge.json")
    database.read()
    assert stat.S_IMODE(database.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(database.path.parent.stat().st_mode) == 0o700


def test_blanking_the_session_secret_signs_everyone_out_exactly_once(tmp_path: Path) -> None:
    # This is the documented "sign every phone out" procedure. If the fresh
    # secret were not written back, every read would mint another one and nobody
    # could sign in again -- a lockout, not a sign-out.
    database = Database(tmp_path / "bridge.json")
    original = database.read().session_secret

    raw = json.loads(database.path.read_text())
    raw["session_secret"] = ""
    database.path.write_text(json.dumps(raw))

    replacement = database.read().session_secret
    assert replacement != original
    assert database.read().session_secret == replacement
    assert json.loads(database.path.read_text())["session_secret"] == replacement


def test_a_failed_write_leaves_the_previous_file_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = Database(tmp_path / "bridge.json")
    with database.update() as state:
        state.snapshot_at = 1234
    good = database.path.read_text()

    def explode(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("checklists_bridge.storage.os.fsync", explode)
    with pytest.raises(OSError), database.update() as state:
        state.snapshot_at = 5678

    assert database.path.read_text() == good
    # And no debris is left behind to be published by a later rename.
    assert list(tmp_path.glob("*.tmp")) == []


def test_a_corrupt_file_says_which_file_and_what_to_do(tmp_path: Path) -> None:
    database = Database(tmp_path / "bridge.json")
    database.read()
    database.path.write_text('{"device_token": "A", ')

    with pytest.raises(StorageError) as caught:
        database.read()
    message = str(caught.value)
    assert str(database.path) in message
    assert "bridge.json.bak" in message


def test_a_file_whose_contents_are_the_wrong_shape_is_refused_cleanly(tmp_path: Path) -> None:
    database = Database(tmp_path / "bridge.json")
    database.read()
    # Valid JSON, wrong shape: a hand-edit that dropped a checklist's id.
    database.path.write_text(json.dumps({"snapshot": [{"name": "no id here"}]}))

    with pytest.raises(StorageError):
        database.read()


def test_each_write_leaves_the_previous_version_beside_it(tmp_path: Path) -> None:
    database = Database(tmp_path / "bridge.json")
    with database.update() as state:
        state.snapshot_at = 111
    with database.update() as state:
        state.snapshot_at = 222

    backup = database.path.with_name("bridge.json.bak")
    assert json.loads(backup.read_text())["snapshot_at"] == 111
    assert json.loads(database.path.read_text())["snapshot_at"] == 222
