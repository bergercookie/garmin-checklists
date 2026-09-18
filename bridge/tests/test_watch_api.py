from __future__ import annotations

from fastapi.testclient import TestClient

import fakes
from checklists_bridge.service import ChecklistService
from conftest import WATCH, configure_fake


def test_watch_endpoints_require_the_device_token(client: TestClient) -> None:
    assert client.get(f"{WATCH}/lists").status_code == 401
    assert client.get(f"{WATCH}/lists", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_index_is_compact_and_lists_item_counts(
    client: TestClient, service: ChecklistService, device_headers: dict[str, str]
) -> None:
    configure_fake(service)
    payload = client.get(f"{WATCH}/lists", headers=device_headers).json()
    assert payload["v"] == 1
    assert payload["t"] > 0
    assert payload["l"] == [
        {"id": "fake:a", "n": "Dive kit", "c": 2},
        {"id": "fake:b", "n": "Travel", "c": 1},
    ]


def test_reading_one_checklist_returns_item_labels(
    client: TestClient, service: ChecklistService, device_headers: dict[str, str]
) -> None:
    configure_fake(service)
    payload = client.get(f"{WATCH}/lists/fake:a", headers=device_headers).json()
    assert payload == {"id": "fake:a", "n": "Dive kit", "i": ["Mask", "Fins"]}


def test_unknown_checklist_is_404(
    client: TestClient, service: ChecklistService, device_headers: dict[str, str]
) -> None:
    configure_fake(service)
    assert client.get(f"{WATCH}/lists/fake:zzz", headers=device_headers).status_code == 404


def test_refresh_flag_pulls_from_the_provider(
    client: TestClient, service: ChecklistService, device_headers: dict[str, str]
) -> None:
    configure_fake(service)
    fakes.CONTENT["a"] = ["Mask", "Fins", "Torch"]

    stale = client.get(f"{WATCH}/lists", headers=device_headers).json()
    assert stale["l"][0]["c"] == 2

    fresh = client.get(f"{WATCH}/lists?refresh=true", headers=device_headers).json()
    assert fresh["l"][0]["c"] == 3


def test_the_watch_api_is_read_only(
    client: TestClient, service: ChecklistService, device_headers: dict[str, str]
) -> None:
    configure_fake(service)
    response = client.post(f"{WATCH}/lists/fake:a", headers=device_headers, json={})
    assert response.status_code == 405


def test_rotating_the_token_locks_the_old_one_out(
    client: TestClient, service: ChecklistService, device_headers: dict[str, str]
) -> None:
    service.rotate_device_token()
    assert client.get(f"{WATCH}/lists", headers=device_headers).status_code == 401


def test_a_percent_encoded_checklist_id_resolves(
    client: TestClient, service: ChecklistService, device_headers: dict[str, str]
) -> None:
    # Connect IQ escapes the ':' in a qualified id when it builds the URL, so
    # the watch really asks for /lists/fake%3Aa. Starlette decodes it back.
    configure_fake(service)
    response = client.get(f"{WATCH}/lists/fake%3Aa", headers=device_headers)
    assert response.status_code == 200
    assert response.json()["n"] == "Dive kit"
