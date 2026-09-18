"""Trilium in a container, seeded over ETAPI.

The whole setup is scriptable, which is what makes this run possible at all:

    POST /set-password          form password1/password2, on a fresh instance
    POST /etapi/auth/login      {"password"} -> {"authToken"}
    POST /etapi/create-note     the notes, with their [] lines
    POST /etapi/attributes      the #checklist label the picker searches for

The seeded note deliberately mixes ticked lines, unticked lines and prose, so
the run proves the parser drops the right ones against a real Trilium rather
than against a fixture of what one is imagined to return.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx

import stack
from providers import Seeded

IMAGE = os.environ.get("TRILIUM_IMAGE", "triliumnext/trilium:v0.105.0")
PORT = 3457
#: Trilium listens on 8080 inside the container whatever the published port is.
INTERNAL_PORT = 8080

PASSWORD = "e2e-trilium-password"
LABEL = "checklist"

NOTE = "Dive kit"
#: What the watch should end up with: the unticked items, in order. Note the
#: mix -- two typed by hand, one made with the editor's checkbox button.
ITEMS = ["Mask and snorkel", "Fins", "Dive computer"]
#: Ticked, so they must never reach the watch: one of each kind.
DONE_TYPED = "Surface marker buoy"
DONE_CLICKED = "Weight belt"


def _editor_item(label: str, *, done: bool = False) -> str:
    """One row exactly as Trilium's own checkbox button writes it.

    Reproduced from a note created in the editor, because this markup carries
    no bracket at all and was therefore invisible to the typed-`[]` rules.
    """
    checked = ' checked="checked"' if done else ""
    return (
        '<li><label class="todo-list__label">'
        f'<input type="checkbox"{checked} disabled="disabled">'
        f'<span class="todo-list__label__description">{label}</span>'
        "</label></li>"
    )


NOTE_BODY = (
    "<h2>Dive kit</h2>"
    "<p>Packed the night before.</p>"
    "<p>[] Mask and snorkel</p>"
    f"<p>[x] {DONE_TYPED}</p>"
    '<ul class="todo-list">'
    f"{_editor_item('Fins')}"
    f"{_editor_item(DONE_CLICKED, done=True)}"
    "</ul>"
    "<p>[] Dive computer</p>"
    "<p>Check the forecast before leaving.</p>"
)

OTHER_NOTE = "Camera bag"
OTHER_BODY = "<p>[] Housing</p><p>[] Strobes</p>"

#: Labelled but empty of checkboxes, so the run can prove a note with no items
#: is offered and simply yields nothing rather than failing the sync.
EMPTY_NOTE = "Trip ideas"
EMPTY_BODY = "<p>Somewhere with a wreck.</p>"

#: Not labelled, so it must not be offered at all.
UNLABELLED_NOTE = "Shopping"
UNLABELLED_BODY = "<p>[] Milk</p>"


class Trilium:
    provider_id = "trilium"
    label = "Trilium Notes"
    container = "checklists-e2e-trilium"

    def __init__(self) -> None:
        self._token = ""
        self._notes: dict[str, str] = {}

    @property
    def _base(self) -> str:
        return f"http://127.0.0.1:{PORT}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": self._token}

    def start(self, workspace: Path) -> str:
        data_dir = workspace / "trilium"
        data_dir.mkdir(parents=True)
        data_dir.chmod(0o777)
        stack.docker_remove(self.container)
        subprocess.run(
            [
                "docker", "run", "-d", "--name", self.container,
                "-e", "TRILIUM_DATA_DIR=/home/node/trilium-data",
                "-v", f"{data_dir}:/home/node/trilium-data",
                "-p", f"127.0.0.1:{PORT}:{INTERNAL_PORT}",
                IMAGE,
            ],
            check=True,
            capture_output=True,
        )  # fmt: skip
        stack.wait_for("trilium", f"{self._base}/")
        return IMAGE.rsplit(":", 1)[-1]

    def seed(self) -> Seeded:
        self._create_document()
        self._set_password()
        self._token = self._login()
        stack.check("ETAPI issued a token", bool(self._token), self._token[:8])

        for title, body, labelled in (
            (NOTE, NOTE_BODY, True),
            (OTHER_NOTE, OTHER_BODY, True),
            (EMPTY_NOTE, EMPTY_BODY, True),
            (UNLABELLED_NOTE, UNLABELLED_BODY, False),
        ):
            self._notes[title] = self._create_note(title, body, labelled=labelled)

        return Seeded(
            config={
                "base_url": self._base,
                "token": self._token,
                "search": f"#{LABEL}",
            },
            source_id=self._notes[NOTE],
            source_name=NOTE,
            items=list(ITEMS),
            other_source_name=OTHER_NOTE,
            also_offered=[EMPTY_NOTE],
            not_offered={UNLABELLED_NOTE: f"it carries no #{LABEL} label"},
            all_source_ids=[self._notes[NOTE], self._notes[OTHER_NOTE]],
        )

    def add_item(self, source_id: str, label: str) -> None:
        """Append one unticked line to the note, as a person editing it would."""
        current = httpx.get(
            f"{self._base}/etapi/notes/{source_id}/content", headers=self._headers, timeout=20
        ).text
        httpx.put(
            f"{self._base}/etapi/notes/{source_id}/content",
            headers={**self._headers, "Content-Type": "text/plain"},
            content=f"{current}<p>[] {label}</p>".encode(),
            timeout=20,
        ).raise_for_status()

    def nothing_was_ticked(self, source_id: str) -> tuple[bool, str]:
        """The note's text must be exactly as seeded, tick marks and all."""
        content = httpx.get(
            f"{self._base}/etapi/notes/{source_id}/content", headers=self._headers, timeout=20
        ).text
        # A leak would show up as an item gaining a tick, in either notation,
        # so both are counted: one seeded `[x]` line and one seeded checkbox.
        typed = content.count("[x]") + content.count("[X]")
        clicked = content.lower().count("checked=")
        return (
            (typed, clicked) == (1, 1),
            f"{typed} ticked line(s) and {clicked} ticked checkbox(es); expected one of each",
        )

    # ------------------------------------------------------------- internals

    def _create_document(self) -> None:
        """Make the database.

        A fresh container serves the setup page but has no tables at all, so
        everything below -- including setting a password -- answers 500 with
        "no such table: options" until this has run. The setup wizard's first
        screen is a choice between a new document and syncing from a server;
        this is the "new document" button.
        """
        response = httpx.post(f"{self._base}/api/setup/new-document", timeout=60)
        stack.check(
            "Trilium created its document",
            response.status_code < 400,
            f"HTTP {response.status_code}: {response.text[:200]}",
        )

    def _set_password(self) -> None:
        """A fresh instance has no password, and ETAPI login needs one."""
        # The tables appear a moment after new-document returns, so this is
        # retried rather than assumed ready.
        deadline = time.time() + 60
        response = None
        while time.time() < deadline:
            response = httpx.post(
                f"{self._base}/set-password",
                data={"password1": PASSWORD, "password2": PASSWORD},
                timeout=30,
                follow_redirects=False,
            )
            if response.status_code < 400:
                break
            time.sleep(2)
        stack.check(
            "Trilium accepted an initial password",
            response is not None and response.status_code < 400,
            f"HTTP {response.status_code}: {response.text[:200]}" if response else "no reply",
        )

    def _login(self) -> str:
        response = httpx.post(
            f"{self._base}/etapi/auth/login", json={"password": PASSWORD}, timeout=30
        )
        response.raise_for_status()
        return str(response.json()["authToken"])

    def _create_note(self, title: str, content: str, *, labelled: bool) -> str:
        created = httpx.post(
            f"{self._base}/etapi/create-note",
            headers=self._headers,
            json={
                "parentNoteId": "root",
                "title": title,
                "type": "text",
                "content": content,
            },
            timeout=20,
        )
        created.raise_for_status()
        note_id = str(created.json()["note"]["noteId"])
        if labelled:
            httpx.post(
                f"{self._base}/etapi/attributes",
                headers=self._headers,
                json={
                    "noteId": note_id,
                    "type": "label",
                    "name": LABEL,
                    "value": "",
                    "isInheritable": False,
                },
                timeout=20,
            ).raise_for_status()
        return note_id
