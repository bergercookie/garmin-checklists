"""Vikunja in a container, seeded over its own API.

Moved here verbatim from full_stack.py when Trilium arrived; the behaviour is
unchanged, which is what makes `just e2e-vikunja` the regression test for that
refactor.
"""

from __future__ import annotations

import os
import secrets
import subprocess
from pathlib import Path

import httpx

import stack
from providers import Seeded

IMAGE = os.environ.get("VIKUNJA_IMAGE", "vikunja/vikunja:2.6.0")
PORT = 3456

USERNAME = "diver"
PASSWORD = "e2e-password-123"
PROJECT = "Dive kit"
ITEMS = ["Mask and snorkel", "Fins", "Dive computer", "Surface marker buoy", "Cutting tool"]
OTHER_PROJECT = "Groceries"
#: A real saved filter, created through /v1/filters -- the same route Vikunja's
#: own settings page uses. Confirmed against a live instance: it shows up in
#: /v2/projects with a negative id (-(filterID + 1)) and its tasks are reached
#: through the identical /projects/{id}/tasks route, no extra token scope.
FILTER = "Open Tasks"
ARCHIVED_PROJECT = "Old gear"


class Vikunja:
    provider_id = "vikunja"
    label = "Vikunja"
    container = "checklists-e2e-vikunja"

    def __init__(self) -> None:
        self._session: dict[str, str] = {}
        self._projects: dict[str, int] = {}

    @property
    def _base(self) -> str:
        return f"http://127.0.0.1:{PORT}/api"

    def start(self, workspace: Path) -> str:
        data_dir = workspace / "vikunja"
        (data_dir / "db").mkdir(parents=True)
        (data_dir / "files").mkdir(parents=True)
        data_dir.chmod(0o777)
        for child in data_dir.iterdir():
            child.chmod(0o777)
        stack.docker_remove(self.container)
        subprocess.run(
            [
                "docker", "run", "-d", "--name", self.container,
                "-e", f"VIKUNJA_SERVICE_PUBLICURL=http://127.0.0.1:{PORT}/",
                "-e", f"VIKUNJA_SERVICE_SECRET={secrets.token_hex(16)}",
                "-e", "VIKUNJA_DATABASE_TYPE=sqlite",
                "-e", "VIKUNJA_DATABASE_PATH=/data/db/vikunja.db",
                "-e", "VIKUNJA_FILES_BASEPATH=/data/files",
                "-e", "VIKUNJA_SERVICE_ENABLEREGISTRATION=true",
                "-v", f"{data_dir}:/data",
                "-p", f"127.0.0.1:{PORT}:{PORT}",
                IMAGE,
            ],
            check=True,
            capture_output=True,
        )  # fmt: skip
        stack.wait_for("vikunja", f"{self._base}/v1/info")
        return str(httpx.get(f"{self._base}/v1/info", timeout=20).json().get("version", "?"))

    def seed(self) -> Seeded:
        """Register a user, mint a read-only API token and create the projects."""
        httpx.post(
            f"{self._base}/v1/register",
            json={"username": USERNAME, "email": "diver@example.com", "password": PASSWORD},
            timeout=20,
        ).raise_for_status()
        jwt = httpx.post(
            f"{self._base}/v1/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=20,
        ).json()["token"]
        self._session = {"Authorization": f"Bearer {jwt}"}

        # Exactly the scopes docs/vikunja.md tells the user to grant -- no more.
        token = httpx.post(
            f"{self._base}/v2/tokens",
            headers=self._session,
            json={
                "title": "checklists-bridge",
                "expires_at": "2030-01-01T00:00:00Z",
                "permissions": {"projects": ["read_all"], "tasks": ["read_all"]},
            },
            timeout=20,
        ).json()["token"]

        for title, items in ((PROJECT, ITEMS), (OTHER_PROJECT, ["Milk", "Coffee"])):
            project_id = httpx.post(
                f"{self._base}/v2/projects",
                headers=self._session,
                json={"title": title},
                timeout=20,
            ).json()["id"]
            self._projects[title] = project_id
            for item in items:
                httpx.post(
                    f"{self._base}/v2/projects/{project_id}/tasks",
                    headers=self._session,
                    json={"title": item},
                    timeout=20,
                ).raise_for_status()

        # A real saved filter -- not declared metadata, an actual object the
        # live API returns and the picker has to see. Filter creation is a v1
        # route; there is no v2 equivalent for it, only for reading one back.
        httpx.put(
            f"{self._base}/v1/filters",
            headers=self._session,
            json={"title": FILTER, "filters": {"filter": "done = false"}},
            timeout=20,
        ).raise_for_status()

        # A project that stays hidden -- proving the *other* exclusion rule
        # (archived) still works now that a negative id no longer means one.
        archived_id = httpx.post(
            f"{self._base}/v2/projects",
            headers=self._session,
            json={"title": ARCHIVED_PROJECT},
            timeout=20,
        ).json()["id"]
        httpx.patch(
            f"{self._base}/v2/projects/{archived_id}",
            headers=self._session,
            json={"is_archived": True},
            timeout=20,
        ).raise_for_status()

        stack.check("API token looks like a Vikunja token", token.startswith("tk_"), token[:8])
        return Seeded(
            config={"base_url": f"http://127.0.0.1:{PORT}", "token": token},
            source_id=str(self._projects[PROJECT]),
            source_name=PROJECT,
            items=list(ITEMS),
            other_source_name=OTHER_PROJECT,
            # Inbox and "My Open Tasks" both ship with every fresh account;
            # the filter created above is the one this test actually controls.
            also_offered=["Inbox", "My Open Tasks (filter)", f"{FILTER} (filter)"],
            not_offered={ARCHIVED_PROJECT: "it was archived after creation"},
            all_source_ids=[str(identifier) for identifier in self._projects.values()],
        )

    def add_item(self, source_id: str, label: str) -> None:
        httpx.post(
            f"{self._base}/v2/projects/{source_id}/tasks",
            headers=self._session,
            json={"title": label},
            timeout=20,
        ).raise_for_status()

    def nothing_was_ticked(self, source_id: str) -> tuple[bool, str]:
        tasks = httpx.get(
            f"{self._base}/v2/projects/{source_id}/tasks",
            headers=self._session,
            timeout=20,
        ).json()["items"]
        return (
            not any(task.get("done") for task in tasks),
            str([(task["title"], task.get("done")) for task in tasks]),
        )
