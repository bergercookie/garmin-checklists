"""Vikunja provider, speaking the v2 API.

Mapping: a Vikunja *project* is a checklist, and each *unfinished* task's title
in it is an item. Tasks already done in Vikunja are left out entirely: a project
with five open and a hundred finished tasks yields a five-item checklist. The
filtering is asked of Vikunja rather than done here, so those hundred are never
transferred.

**Saved filters count as checklists too.** Vikunja represents a saved filter as
a pseudo-project with a negative id -- the id is ``-(filterID + 1)``, confirmed
against a real instance -- and ``GET /projects/{id}/tasks`` on that pseudo-id
serves exactly the tasks the filter's own query matches, through the identical
route and the identical token scopes as a real project. Nothing about fetching
one is different, so nothing about fetching one is special-cased; only the
picker marks it, by appending " (filter)" to the name it offers (see
``list_sources``). Every account gets a built-in filter called "My Open Tasks",
which is why that name shows up in the tests below.

Ticks made on the watch are a separate thing and never travel back, so a task is
"done" only if Vikunja says so.

API reference (Vikunja >= 2.4):
    GET {base}/api/v2/projects?page=&per_page=
    GET {base}/api/v2/projects/{project}/tasks
        ?page=&per_page=&sort_by=id&order_by=asc&filter=done+%3D+false
    Authorization: Bearer tk_...
Both endpoints return ``{"items": [...], "total": n, "page": n, "per_page": n,
"total_pages": n}``. ``{project}`` is a real project's id or a filter's
pseudo-id; the response shape and every query parameter are identical either
way.

Only those two routes are used, deliberately: an API token scoped to
``read_all`` on Projects and Tasks can reach them, whereas the single-project
route ``GET /projects/{id}`` additionally needs ``read_one`` and returns 401
without it. This also covers filters -- reaching one needs no scope beyond
Projects/Tasks ``read_all``, confirmed against a real instance rather than
assumed.

Tasks are ordered by id, i.e. the order they were created. Vikunja's manual
ordering lives in ``position``, which is per-view: sorting by it requires the
``/projects/{project}/views/{view}/tasks`` route, and listing views is not a
permission an API token can hold. Asking for ``sort_by=position`` here fails
with HTTP 400, "You must provide a project view ID when sorting by position".
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any, ClassVar

import httpx

from checklists_bridge.models import Checklist, SourceRef, clean_items, clean_name
from checklists_bridge.providers.base import (
    ProviderAuthError,
    ProviderUnavailableError,
    SourceNotFoundError,
    TaskProvider,
    checked_base_url,
)
from checklists_bridge.providers.registry import REGISTRY, ConfigField, ProviderSpec

LOGGER = logging.getLogger(__name__)

API_PREFIX = "/api/v2"
#: Asks Vikunja for open tasks only, so a long history is never transferred.
DONE_FILTER = "done = false"
PAGE_SIZE = 100
#: Stop after this many pages so a misbehaving server cannot hang a sync.
MAX_PAGES = 20
REQUEST_TIMEOUT = 15.0


class VikunjaProvider(TaskProvider):
    id: ClassVar[str] = "vikunja"
    label: ClassVar[str] = "Vikunja"

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = checked_base_url(
            base_url, service="Vikunja", example="https://vikunja.example.com"
        )
        self._token = token.strip()
        self._client = client or httpx.Client(timeout=REQUEST_TIMEOUT)
        #: Projects are listed once per provider instance. The service builds a
        #: fresh provider for each refresh, so this cannot go stale between one
        #: sync and the next.
        self._projects_cache: list[dict[str, Any]] | None = None

    def close(self) -> None:
        self._client.close()

    def list_sources(self) -> list[SourceRef]:
        return [
            SourceRef(id=str(project["id"]), name=self._picker_name(project))
            for project in self._projects()
            if self._is_importable(project)
        ]

    @staticmethod
    def _is_importable(project: dict[str, Any]) -> bool:
        """Exclude only archived projects. Saved filters are offered."""
        return not project.get("is_archived")

    @staticmethod
    def _picker_name(project: dict[str, Any]) -> str:
        """The picker's label. Marked, so a filter cannot be mistaken for a
        project of the same name -- its tasks may span several of them.

        Cosmetic only: the checklist's own name, set in ``fetch()`` via
        ``_project_title``, is never decorated, so the marker never reaches
        the watch face.
        """
        title = str(project.get("title", ""))
        is_filter = int(project.get("id", 0)) < 0
        return f"{title} (filter)" if is_filter else title

    def fetch(self, source_id: str) -> Checklist:
        titles = [
            str(task.get("title", ""))
            for task in self._paginate(
                f"/projects/{source_id}/tasks",
                params={"sort_by": "id", "order_by": "asc", "filter": DONE_FILTER},
            )
            # Belt and braces: the filter above is what keeps finished tasks off
            # the wire, but an older server that ignored it must not leak them.
            if not task.get("done")
        ]
        return Checklist(
            id=str(source_id),
            name=clean_name(self._project_title(source_id)),
            items=clean_items(titles),
        )

    def _projects(self) -> list[dict[str, Any]]:
        """Every project, fetched at most once per provider instance."""
        if self._projects_cache is None:
            self._projects_cache = list(self._paginate("/projects"))
        return self._projects_cache

    def _project_title(self, source_id: str) -> str:
        """Resolve a title from the project list.

        Archived projects are hidden from the import picker but still resolve
        here, so a checklist imported before archiving keeps its name.
        """
        for project in self._projects():
            if str(project.get("id")) == str(source_id):
                title = str(project.get("title", "")).strip()
                if title:
                    return title
        return f"Project {source_id}"

    def _paginate(
        self, path: str, params: Mapping[str, Any] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Yield every ``items`` entry across pages of a v2 list endpoint.

        Stopping correctly is the whole difficulty. A server may cap `per_page`
        below what we asked for -- Vikunja's `maxitemsperpage` defaults to 50 in
        several packagings -- so a short page does not mean a last page, and
        comparing against the requested size silently truncates the list to one
        page. It may also omit `total_pages` entirely. An empty page is the only
        reliable end, so that is what this waits for.
        """
        for page in range(1, MAX_PAGES + 1):
            payload = self._get(path, {**(params or {}), "page": page, "per_page": PAGE_SIZE})
            items = payload.get("items") or []
            yield from items
            if not items:
                return
            total_pages = int(payload.get("total_pages") or 0)
            if total_pages and page >= total_pages:
                return
            # The size the server chose, not the one we asked for.
            served = int(payload.get("per_page") or 0) or PAGE_SIZE
            if len(items) < served:
                return
        LOGGER.warning(
            "stopped paginating %s after %d pages; the list may be incomplete", path, MAX_PAGES
        )

    def _get(self, path: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{API_PREFIX}{path}"
        try:
            response = self._client.get(
                url,
                params=dict(params or {}),
                headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
            )
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(f"could not reach Vikunja at {url}: {error}") from error

        if response.status_code in (401, 403):
            raise ProviderAuthError("Vikunja rejected the API token (check its scopes)")
        if response.status_code == 404:
            raise SourceNotFoundError(f"Vikunja has nothing at {path}")
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                f"Vikunja returned HTTP {response.status_code} for {path}"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderUnavailableError(f"Vikunja sent a non-JSON reply for {path}") from error
        if not isinstance(payload, dict):
            raise ProviderUnavailableError(f"Vikunja sent an unexpected reply for {path}")
        return payload


def _factory(config: Mapping[str, Any]) -> VikunjaProvider:
    return VikunjaProvider(
        base_url=str(config["base_url"]),
        token=str(config["token"]),
        client=config.get("client"),
    )


SPEC = REGISTRY.register(
    ProviderSpec(
        id=VikunjaProvider.id,
        label=VikunjaProvider.label,
        description="Import Vikunja projects as checklist templates.",
        factory=_factory,
        config_fields=(
            ConfigField(
                name="base_url",
                label="Vikunja URL",
                kind="url",
                placeholder="https://vikunja.example.com",
                help="Root URL of your instance, without /api.",
            ),
            ConfigField(
                name="token",
                label="API token",
                kind="password",
                placeholder="tk_...",
                help="Vikunja > Settings > API tokens. Read access to projects and tasks.",
            ),
        ),
    )
)
