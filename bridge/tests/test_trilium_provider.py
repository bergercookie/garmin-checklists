"""The Trilium provider against a stubbed ETAPI. No network, no container."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from checklists_bridge.models import MAX_ITEMS_PER_CHECKLIST
from checklists_bridge.providers.base import (
    ProviderAuthError,
    ProviderError,
    ProviderUnavailableError,
    SourceNotFoundError,
)
from checklists_bridge.providers.trilium import (
    DEFAULT_SEARCH,
    MAX_NOTES,
    SPEC,
    TriliumProvider,
)
from conftest import fake_trilium

SEARCH = "/etapi/notes"


def note(note_id: str, title: str, **extra: Any) -> dict[str, Any]:
    return {"noteId": note_id, "title": title, "type": "text", "isProtected": False, **extra}


def results(*notes: dict[str, Any]) -> dict[str, Any]:
    return {"results": list(notes)}


def test_sources_are_the_notes_the_search_returned() -> None:
    provider = fake_trilium(
        {SEARCH: results(note("abc123", "Dive kit"), note("def456", "Packing"))}
    )
    assert [(source.id, source.name) for source in provider.list_sources()] == [
        ("abc123", "Dive kit"),
        ("def456", "Packing"),
    ]


def test_the_default_search_offers_labelled_notes() -> None:
    seen: dict[str, Any] = {}

    def route(request: httpx.Request) -> dict[str, Any]:
        seen.update(request.url.params)
        return results(note("abc123", "Dive kit"))

    fake_trilium({SEARCH: route}).list_sources()
    assert seen["search"] == DEFAULT_SEARCH
    assert seen["limit"] == str(MAX_NOTES)
    # A stable order, so the picker does not reshuffle between visits.
    assert seen["orderBy"] == "title"


def test_the_search_can_be_replaced() -> None:
    seen: dict[str, Any] = {}

    def route(request: httpx.Request) -> dict[str, Any]:
        seen.update(request.url.params)
        return results()

    fake_trilium({SEARCH: route}, search="#packing OR #dive").list_sources()
    assert seen["search"] == "#packing OR #dive"


def test_a_blank_search_falls_back_to_the_default() -> None:
    seen: dict[str, Any] = {}

    def route(request: httpx.Request) -> dict[str, Any]:
        seen.update(request.url.params)
        return results()

    fake_trilium({SEARCH: route}, search="   ").list_sources()
    assert seen["search"] == DEFAULT_SEARCH


def test_protected_notes_are_not_offered() -> None:
    # Their content is encrypted at rest and unreadable over ETAPI, so importing
    # one would give an empty checklist and no explanation.
    provider = fake_trilium(
        {SEARCH: results(note("abc123", "Secret", isProtected=True), note("def456", "Dive kit"))}
    )
    assert [source.name for source in provider.list_sources()] == ["Dive kit"]


def test_notes_that_cannot_hold_text_are_not_offered() -> None:
    provider = fake_trilium(
        {SEARCH: results(note("abc123", "Photo", type="image"), note("def456", "Dive kit"))}
    )
    assert [source.name for source in provider.list_sources()] == ["Dive kit"]


def test_a_note_without_an_id_is_skipped_rather_than_crashing() -> None:
    provider = fake_trilium(
        {SEARCH: {"results": [{"title": "Broken"}, note("def456", "Dive kit")]}}
    )
    assert [source.name for source in provider.list_sources()] == ["Dive kit"]


def test_fetch_turns_the_note_body_into_items() -> None:
    provider = fake_trilium(
        {
            "/etapi/notes/abc123": note("abc123", "Dive kit"),
            "/etapi/notes/abc123/content": "<p>[] Mask</p><p>[x] Fins</p><p>[] Reel</p>",
        }
    )
    checklist = provider.fetch("abc123")
    assert checklist.id == "abc123"
    assert checklist.name == "Dive kit"
    # The ticked line never reaches the watch.
    assert checklist.items == ("Mask", "Reel")


def test_fetch_reads_the_note_directly_rather_than_the_search_results() -> None:
    # So a note whose #checklist label was removed after importing keeps its
    # name and keeps syncing, instead of degrading to a placeholder.
    provider = fake_trilium(
        {
            SEARCH: results(),
            "/etapi/notes/abc123": note("abc123", "Dive kit"),
            "/etapi/notes/abc123/content": "<p>[] Mask</p>",
        }
    )
    assert provider.fetch("abc123").name == "Dive kit"


def test_a_note_with_no_checkboxes_gives_an_empty_checklist() -> None:
    provider = fake_trilium(
        {
            "/etapi/notes/abc123": note("abc123", "Thoughts"),
            "/etapi/notes/abc123/content": "<p>Nothing to pack.</p>",
        }
    )
    assert provider.fetch("abc123").items == ()


def test_a_note_with_no_title_gets_a_readable_placeholder() -> None:
    provider = fake_trilium(
        {
            "/etapi/notes/abc123": {"noteId": "abc123", "title": ""},
            "/etapi/notes/abc123/content": "<p>[] Mask</p>",
        }
    )
    assert provider.fetch("abc123").name == "Note abc123"


def test_a_very_long_note_is_capped_at_the_watch_limit() -> None:
    body = "".join(f"<p>[] item {index}</p>" for index in range(MAX_ITEMS_PER_CHECKLIST + 50))
    provider = fake_trilium(
        {
            "/etapi/notes/abc123": note("abc123", "Long"),
            "/etapi/notes/abc123/content": body,
        }
    )
    assert len(provider.fetch("abc123").items) == MAX_ITEMS_PER_CHECKLIST


def test_the_token_travels_bare_not_as_a_bearer() -> None:
    # Trilium only started accepting "Bearer <token>" in 0.93; the bare form
    # works on every version.
    seen: dict[str, Any] = {}

    def route(request: httpx.Request) -> dict[str, Any]:
        seen["authorization"] = request.headers.get("authorization")
        return results()

    fake_trilium({SEARCH: route}, token="etapi-secret").list_sources()
    assert seen["authorization"] == "etapi-secret"


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, ProviderAuthError),
        (403, ProviderAuthError),
        (404, SourceNotFoundError),
        (500, ProviderUnavailableError),
    ],
)
def test_http_failures_map_to_the_error_taxonomy(status: int, expected: type[Exception]) -> None:
    provider = fake_trilium({SEARCH: (status, {"message": "no"})})
    with pytest.raises(expected):
        provider.list_sources()


def test_a_deleted_note_is_reported_as_a_missing_source() -> None:
    provider = fake_trilium({SEARCH: results()})
    with pytest.raises(SourceNotFoundError):
        provider.fetch("gone")


def test_a_transport_failure_is_reported_as_unavailable() -> None:
    def explode(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    client = httpx.Client(transport=httpx.MockTransport(explode))
    provider = TriliumProvider("https://trilium.example.com", "t", client=client)
    with pytest.raises(ProviderUnavailableError, match="could not reach Trilium"):
        provider.list_sources()


def test_a_reply_that_is_not_json_is_reported_rather_than_raising_valueerror() -> None:
    provider = fake_trilium({SEARCH: "<html>login page</html>"})
    with pytest.raises(ProviderUnavailableError, match="did not answer"):
        provider.list_sources()


def test_a_reply_without_a_results_list_is_reported() -> None:
    provider = fake_trilium({SEARCH: {"note": "wrong shape"}})
    with pytest.raises(ProviderUnavailableError, match="results"):
        provider.list_sources()


def test_a_reply_that_is_a_list_rather_than_an_object_is_reported() -> None:
    provider = fake_trilium({SEARCH: [1, 2, 3]})
    with pytest.raises(ProviderUnavailableError):
        provider.list_sources()


@pytest.mark.parametrize("base_url", ["file:///etc/passwd", "trilium.example.com", ""])
def test_a_url_that_could_never_work_is_refused_up_front(base_url: str) -> None:
    with pytest.raises(ProviderError, match="usable Trilium URL"):
        TriliumProvider(base_url, "t")


def test_the_registry_entry_builds_a_working_provider() -> None:
    provider = SPEC.build(
        {"base_url": "https://trilium.example.com", "token": "etapi-secret", "search": "#kit"}
    )
    assert isinstance(provider, TriliumProvider)
    provider.close()


def test_the_search_field_is_optional_so_setup_is_two_inputs() -> None:
    provider = SPEC.build({"base_url": "https://trilium.example.com", "token": "etapi-secret"})
    assert isinstance(provider, TriliumProvider)
    provider.close()


def test_closing_the_provider_closes_its_client() -> None:
    provider = fake_trilium({SEARCH: results()})
    assert not provider._api._client.is_closed
    provider.close()
    assert provider._api._client.is_closed


def test_a_refusal_from_trilium_names_the_token() -> None:
    # Trilium answers a bad token with 401 and its own JSON error body.
    provider = fake_trilium(
        {
            SEARCH: (
                401,
                {"status": 401, "code": "NOT_AUTHENTICATED", "message": "Not authenticated"},
            )
        }
    )
    with pytest.raises(ProviderAuthError, match="rejected the ETAPI token"):
        provider.list_sources()


def test_a_refusal_from_in_front_of_trilium_says_so_instead() -> None:
    # A 403 cannot have come from the ETAPI -- it answers 401 for auth, never
    # 403 -- so reporting "your token is wrong" sends people to check a token
    # that was never the problem. Verified against a real instance.
    def deny(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, html="<html>Access denied</html>")

    provider = fake_trilium({SEARCH: deny})
    with pytest.raises(ProviderAuthError, match="in front of Trilium"):
        provider.list_sources()


def test_a_401_that_is_not_trilium_shaped_is_also_blamed_on_the_proxy() -> None:
    def deny(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, html="<html>Sign in to continue</html>")

    provider = fake_trilium({SEARCH: deny})
    with pytest.raises(ProviderAuthError, match="in front of Trilium"):
        provider.list_sources()
