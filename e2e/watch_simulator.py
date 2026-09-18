"""A stand-in for the Connect IQ app, faithful to watch/source/*.mc.

This is NOT the Garmin simulator: the Connect IQ SDK cannot be installed here.
It re-implements the watch's *observable behaviour* -- the exact HTTP calls
SyncTask.mc makes, the storage shape Store.mc writes, and the labels the menus
render -- so the end-to-end run exercises the real contract between the bridge
and the watch.

To stop it drifting into a parallel fiction, :func:`assert_matches_monkey_c`
reads the Monkey C sources and fails if they no longer agree with what this
file does.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

WATCH_SOURCE = Path(__file__).resolve().parent.parent / "watch" / "source"

#: Mirrors SyncTask.mc.
INDEX_PATH = "/api/v1/watch/lists"
LIST_PATH = "/api/v1/watch/lists/{id}"

#: Mirrors the dictionary Store.mc persists.
KEY_ID, KEY_NAME, KEY_ITEMS, KEY_DONE = "id", "n", "i", "d"


class WatchError(RuntimeError):
    """What the watch would show on its home screen instead of a sync result."""


class Watch:
    """The watch's persistent state plus the two things the user can do."""

    def __init__(self, bridge_url: str, device_token: str) -> None:
        self._bridge_url = bridge_url.rstrip("/")
        self._device_token = device_token
        self.checklists: list[dict[str, Any]] = []
        self.synced_at: int | None = None
        self.requests: list[str] = []

    # -- SyncTask.mc ---------------------------------------------------------

    def sync(self) -> str:
        """Fetch the index, then one request per checklist, then replace all."""
        index = self._get(f"{INDEX_PATH}?refresh=true")
        collected = [self._get(LIST_PATH.format(id=entry[KEY_ID])) for entry in index["l"]]
        self._replace_all(collected)
        self.synced_at = index["t"]
        return "Sync complete"

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._bridge_url}{path}"
        self.requests.append(path)
        response = httpx.get(
            url, headers={"Authorization": f"Bearer {self._device_token}"}, timeout=15
        )
        if response.status_code in (401, 403):
            raise WatchError("Token rejected")
        if response.status_code != 200:
            raise WatchError(f"Sync failed ({response.status_code})")
        return dict(response.json())

    # -- Store.mc ------------------------------------------------------------

    def _replace_all(self, fetched: list[dict[str, Any]]) -> None:
        """Every sync replaces the lot and clears every tick, by design."""
        self.checklists = [
            {
                KEY_ID: item[KEY_ID],
                KEY_NAME: item[KEY_NAME],
                KEY_ITEMS: list(item[KEY_ITEMS]),
                KEY_DONE: [False] * len(item[KEY_ITEMS]),
            }
            for item in fetched
        ]

    def set_ticked(self, list_index: int, item_index: int, ticked: bool) -> None:
        """Ticking is local and never leaves the watch."""
        self.checklists[list_index][KEY_DONE][item_index] = ticked

    # -- IndexMenu.mc / ItemsMenu.mc ----------------------------------------

    def index_menu(self) -> list[str]:
        """What the checklist menu shows, including the trailing Sync and Settings entries."""
        rows = [
            f"{item[KEY_NAME]}  ({sum(item[KEY_DONE])}/{len(item[KEY_DONE])} done)"
            for item in self.checklists
        ]
        return [*rows, "Sync now", "Settings"]

    def items_menu(self, list_index: int) -> list[str]:
        checklist = self.checklists[list_index]
        return [
            f"[{'x' if done else ' '}] {label}"
            for label, done in zip(checklist[KEY_ITEMS], checklist[KEY_DONE], strict=True)
        ]


def assert_matches_monkey_c() -> list[str]:
    """Fail if the Monkey C sources no longer match this simulator."""
    sync = (WATCH_SOURCE / "SyncTask.mc").read_text()
    store = (WATCH_SOURCE / "Store.mc").read_text()
    checks = [
        (f"SyncTask.mc requests {INDEX_PATH}", f'"{INDEX_PATH}"' in sync),
        ("SyncTask.mc asks the bridge to refresh", '"refresh" => "true"' in sync),
        ("SyncTask.mc reads the index under key 'l'", 'data["l"]' in sync),
        ("SyncTask.mc reads list ids under key 'id'", 'entry["id"]' in sync),
        *[
            (f"Store.mc persists key {key!r}", f'"{key}"' in store)
            for key in (KEY_ID, KEY_NAME, KEY_ITEMS, KEY_DONE)
        ],
        (
            "Store.replaceAll clears ticks",
            re.search(r"unticked\(items\.size\(\)\)", store) is not None,
        ),
    ]
    failures = [name for name, ok in checks if not ok]
    if failures:
        raise AssertionError("watch simulator has drifted from Monkey C: " + "; ".join(failures))
    return [name for name, _ in checks]
