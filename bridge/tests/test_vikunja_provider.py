from __future__ import annotations

from typing import Any

import httpx
import pytest

from checklists_bridge.models import MAX_ITEMS_PER_CHECKLIST
from checklists_bridge.providers.base import (
    ProviderAuthError,
    ProviderUnavailableError,
    SourceNotFoundError,
)
from checklists_bridge.providers.vikunja import (
    DONE_FILTER,
    MAX_PAGES,
    PAGE_SIZE,
    SPEC,
    VikunjaProvider,
)
from conftest import fake_vikunja, page


def test_list_sources_uses_the_v2_projects_endpoint() -> None:
    provider = fake_vikunja(
        {"/api/v2/projects": page([{"id": 12, "title": "Dive kit"}, {"id": 13, "title": "Travel"}])}
    )
    sources = provider.list_sources()
    assert [(source.id, source.name) for source in sources] == [
        ("12", "Dive kit"),
        ("13", "Travel"),
    ]


def test_saved_filters_are_offered_marked_as_such() -> None:
    # Vikunja returns saved filters from /projects with a negative id, and
    # fetches their tasks through the identical /projects/{id}/tasks route --
    # confirmed against a real instance, so they are offered like any project.
    # The marker distinguishes them, since a filter's tasks can span several
    # projects and its title alone does not say so.
    provider = fake_vikunja(
        {
            "/api/v2/projects": page(
                [{"id": 1, "title": "Inbox"}, {"id": -2, "title": "My Open Tasks"}]
            )
        }
    )
    sources = {source.name: source.id for source in provider.list_sources()}
    assert sources == {"Inbox": "1", "My Open Tasks (filter)": "-2"}


def test_a_filters_own_name_is_unmarked_on_the_watch() -> None:
    # The "(filter)" suffix is picker decoration only; fetch() must not carry
    # it into the checklist name the watch actually displays.
    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": -2, "title": "My Open Tasks"}]),
            "/api/v2/projects/-2/tasks": page([{"id": 1, "title": "Call the dentist"}]),
        }
    )
    checklist = provider.fetch("-2")
    assert checklist.name == "My Open Tasks"
    assert checklist.items == ("Call the dentist",)


def test_a_filter_is_fetched_through_the_same_tasks_route_as_a_project() -> None:
    seen_paths: list[str] = []

    def route(request: httpx.Request) -> dict[str, Any]:
        seen_paths.append(request.url.path)
        return {"items": [{"id": 1, "title": "Renew passport"}], "total_pages": 1}

    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": -2, "title": "My Open Tasks"}]),
            "/api/v2/projects/-2/tasks": route,
        }
    )
    provider.fetch("-2")
    assert seen_paths == ["/api/v2/projects/-2/tasks"]


def test_an_archived_filter_and_project_are_both_still_excluded() -> None:
    # The two exclusion rules -- archived, and (now removed) negative-id --
    # must not interfere with each other.
    provider = fake_vikunja(
        {
            "/api/v2/projects": page(
                [
                    {"id": 1, "title": "Live"},
                    {"id": 13, "title": "Old project", "is_archived": True},
                    {"id": -2, "title": "My Open Tasks"},
                    {"id": -5, "title": "Old filter", "is_archived": True},
                ]
            )
        }
    )
    assert [source.name for source in provider.list_sources()] == [
        "Live",
        "My Open Tasks (filter)",
    ]


def test_tasks_are_requested_in_creation_order_not_position() -> None:
    # sort_by=position needs a view id and answers 400 on this route.
    seen: dict[str, Any] = {}

    def tasks(request: httpx.Request) -> dict[str, Any]:
        seen.update(request.url.params)
        return page([{"id": 1, "title": "Mask"}])

    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": 12, "title": "Dive kit"}]),
            "/api/v2/projects/12/tasks": tasks,
        }
    )
    provider.fetch("12")
    assert seen["sort_by"] == "id"
    assert seen["order_by"] == "asc"


def test_list_sources_skips_archived_projects() -> None:
    provider = fake_vikunja(
        {
            "/api/v2/projects": page(
                [{"id": 12, "title": "Live"}, {"id": 13, "title": "Old", "is_archived": True}]
            )
        }
    )
    assert [source.name for source in provider.list_sources()] == ["Live"]


def test_fetch_maps_task_titles_to_items() -> None:
    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": 12, "title": "Dive kit"}]),
            "/api/v2/projects/12/tasks": page(
                [{"id": 1, "title": "Mask"}, {"id": 2, "title": "Fins"}]
            ),
        }
    )
    checklist = provider.fetch("12")
    assert checklist.id == "12"
    assert checklist.name == "Dive kit"
    assert checklist.items == ("Mask", "Fins")


def test_finished_tasks_never_reach_the_checklist() -> None:
    seen: dict[str, Any] = {}

    def tasks(request: httpx.Request) -> dict[str, Any]:
        seen.update(request.url.params)
        # A server that ignored the filter must still not leak finished tasks.
        return page(
            [
                {"id": 1, "title": "Mask"},
                {"id": 2, "title": "Old strap", "done": True},
                {"id": 3, "title": "Fins", "done": False},
            ]
        )

    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": 12, "title": "Dive kit"}]),
            "/api/v2/projects/12/tasks": tasks,
        }
    )
    assert provider.fetch("12").items == ("Mask", "Fins")
    # And the work is asked of Vikunja, so the history is never transferred.
    assert seen["filter"] == DONE_FILTER


def test_list_sources_follows_pagination() -> None:
    pages: dict[str, list[dict[str, Any]]] = {
        "1": [{"id": index, "title": f"Project {index}"} for index in range(1, PAGE_SIZE + 1)],
        "2": [{"id": 999, "title": "Last"}],
    }

    def projects(request: httpx.Request) -> dict[str, Any]:
        number = request.url.params.get("page", "1")
        return {
            "items": pages[number],
            "total": PAGE_SIZE + 1,
            "page": int(number),
            "per_page": PAGE_SIZE,
            "total_pages": 2,
        }

    sources = fake_vikunja({"/api/v2/projects": projects}).list_sources()
    assert len(sources) == PAGE_SIZE + 1
    assert sources[-1].name == "Last"


def test_fetch_caps_items_so_the_watch_cannot_be_flooded() -> None:
    tasks = [
        {"id": index, "title": f"Item {index}"} for index in range(MAX_ITEMS_PER_CHECKLIST + 5)
    ]
    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": 12, "title": "Big"}]),
            "/api/v2/projects/12/tasks": page(tasks),
        }
    )
    assert len(provider.fetch("12").items) == MAX_ITEMS_PER_CHECKLIST


def test_requests_carry_the_bearer_token() -> None:
    seen: dict[str, Any] = {}

    def projects(request: httpx.Request) -> dict[str, Any]:
        seen["auth"] = request.headers["authorization"]
        return page([])

    fake_vikunja({"/api/v2/projects": projects}).list_sources()
    assert seen["auth"] == "Bearer tk_secret"


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [(401, ProviderAuthError), (403, ProviderAuthError), (500, ProviderUnavailableError)],
)
def test_http_errors_map_to_provider_errors(status_code: int, expected: type[Exception]) -> None:
    provider = fake_vikunja({"/api/v2/projects": (status_code, {"message": "no"})})
    with pytest.raises(expected):
        provider.list_sources()


def test_missing_project_raises_source_not_found() -> None:
    provider = fake_vikunja({"/api/v2/projects": page([])})
    with pytest.raises(SourceNotFoundError):
        provider.fetch("404")


def test_transport_failure_is_reported_as_unavailable() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    provider = VikunjaProvider(
        "https://vikunja.example.com",
        "tk_secret",
        client=httpx.Client(transport=httpx.MockTransport(boom)),
    )
    with pytest.raises(ProviderUnavailableError):
        provider.list_sources()


def test_a_non_json_reply_is_reported_as_unavailable() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>login page</html>")

    provider = VikunjaProvider(
        "https://vikunja.example.com",
        "tk_secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderUnavailableError):
        provider.list_sources()


def test_a_reply_that_is_not_an_object_is_reported_as_unavailable() -> None:
    provider = fake_vikunja({"/api/v2/projects": [{"id": 1}]})
    with pytest.raises(ProviderUnavailableError):
        provider.list_sources()


def test_pagination_stops_at_the_page_guard() -> None:
    # A server that always claims another page must not hang the sync.
    requested: list[str | None] = []

    def projects(request: httpx.Request) -> dict[str, Any]:
        requested.append(request.url.params.get("page"))
        return {
            "items": [{"id": index, "title": f"P{index}"} for index in range(1, PAGE_SIZE + 1)],
            "total": 10**6,
            "page": int(request.url.params.get("page", "1")),
            "per_page": PAGE_SIZE,
            "total_pages": 10**6,
        }

    sources = fake_vikunja({"/api/v2/projects": projects}).list_sources()
    assert len(requested) == MAX_PAGES
    assert len(sources) == MAX_PAGES * PAGE_SIZE


def test_the_registry_factory_builds_a_working_provider() -> None:
    provider = SPEC.build({"base_url": "https://vikunja.example.com/", "token": "tk_secret"})
    assert isinstance(provider, VikunjaProvider)


def test_fetch_never_touches_the_single_project_route() -> None:
    # That route needs the read_one token scope; the docs only ask for read_all.
    seen: list[str] = []

    def projects(request: httpx.Request) -> dict[str, Any]:
        seen.append(str(request.url.path))
        return page([{"id": 12, "title": "Dive kit"}])

    def tasks(request: httpx.Request) -> dict[str, Any]:
        seen.append(str(request.url.path))
        return page([{"id": 1, "title": "Mask"}])

    provider = fake_vikunja({"/api/v2/projects": projects, "/api/v2/projects/12/tasks": tasks})
    provider.fetch("12")
    assert "/api/v2/projects/12" not in seen


def test_the_project_list_is_fetched_once_per_instance() -> None:
    calls: list[int] = []

    def projects(_request: httpx.Request) -> dict[str, Any]:
        calls.append(1)
        return page([{"id": 12, "title": "Dive kit"}, {"id": 13, "title": "Travel"}])

    provider = fake_vikunja(
        {
            "/api/v2/projects": projects,
            "/api/v2/projects/12/tasks": page([{"id": 1, "title": "Mask"}]),
            "/api/v2/projects/13/tasks": page([{"id": 2, "title": "Passport"}]),
        }
    )
    provider.list_sources()
    assert provider.fetch("12").name == "Dive kit"
    assert provider.fetch("13").name == "Travel"
    assert len(calls) == 1


def test_an_archived_project_keeps_its_name_after_import() -> None:
    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": 12, "title": "Dive kit", "is_archived": True}]),
            "/api/v2/projects/12/tasks": page([{"id": 1, "title": "Mask"}]),
        }
    )
    assert provider.list_sources() == []
    assert provider.fetch("12").name == "Dive kit"


def test_an_unknown_project_falls_back_to_a_placeholder_name() -> None:
    provider = fake_vikunja(
        {
            "/api/v2/projects": page([]),
            "/api/v2/projects/99/tasks": page([{"id": 1, "title": "Mask"}]),
        }
    )
    assert provider.fetch("99").name == "Project 99"


def test_a_project_with_a_blank_title_falls_back_to_a_placeholder() -> None:
    provider = fake_vikunja(
        {
            "/api/v2/projects": page([{"id": 12, "title": "   "}]),
            "/api/v2/projects/12/tasks": page([{"id": 1, "title": "Mask"}]),
        }
    )
    assert provider.fetch("12").name == "Project 12"


def test_pagination_survives_a_server_that_caps_the_page_size() -> None:
    # Vikunja's maxitemsperpage defaults to 50 in several packagings, so asking
    # for 100 and getting 50 is normal -- and used to be read as "last page",
    # silently truncating a 500-project instance to its first 50.
    served = 50
    projects = [{"id": index, "title": f"p{index}"} for index in range(1, 121)]

    def route(request: httpx.Request) -> dict[str, Any]:
        number = int(request.url.params["page"])
        window = projects[(number - 1) * served : number * served]
        return {"items": window, "per_page": served, "total_pages": 0}

    provider = fake_vikunja({"/api/v2/projects": route})
    assert len(provider.list_sources()) == len(projects)


def test_pagination_survives_a_server_that_omits_the_page_count() -> None:
    projects = [{"id": index, "title": f"p{index}"} for index in range(1, 251)]

    def route(request: httpx.Request) -> dict[str, Any]:
        number = int(request.url.params["page"])
        return {"items": projects[(number - 1) * 100 : number * 100]}

    provider = fake_vikunja({"/api/v2/projects": route})
    assert len(provider.list_sources()) == len(projects)


def test_the_http_client_is_closed_when_the_provider_is_done() -> None:
    # A provider is built fresh for every refresh, so one that never closes its
    # pool leaks sockets for as long as the bridge runs.
    provider = fake_vikunja({"/api/v2/projects": page([])})
    assert not provider._client.is_closed
    provider.close()
    assert provider._client.is_closed
