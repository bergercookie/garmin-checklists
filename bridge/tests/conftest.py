"""Shared fixtures: a throwaway database, service and API client per test."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

import fakes
from checklists_bridge.config import Settings
from checklists_bridge.providers import local
from checklists_bridge.providers.registry import ProviderRegistry
from checklists_bridge.providers.trilium import TriliumProvider
from checklists_bridge.providers.vikunja import VikunjaProvider
from checklists_bridge.service import ChecklistService
from checklists_bridge.storage import Database
from checklists_bridge.web import create_app

ADMIN_PASSWORD = "hunter2"

# The version lives in the prefix, so a v2 is a one-line change here rather
# than a search-and-replace across the suite. Paths below these stay literal:
# a test should show the route it exercises.
ADMIN = "/api/v1/admin"
WATCH = "/api/v1/watch"


@pytest.fixture
def database(tmp_path: Path) -> Database:
    return Database(tmp_path / "bridge.json")


@pytest.fixture
def registry() -> ProviderRegistry:
    """Real local provider plus an in-memory stand-in for a remote one."""
    fakes.reset({"a": ("Dive kit", ["Mask", "Fins"]), "b": ("Travel", ["Passport"])})
    catalogue = ProviderRegistry()
    catalogue.register(local.SPEC)
    catalogue.register(fakes.SPEC)
    return catalogue


@pytest.fixture
def service(database: Database, registry: ProviderRegistry) -> ChecklistService:
    return ChecklistService(database, registry)


def configure_fake(service: ChecklistService) -> Any:
    """Connect the fake provider and import both of its sources."""
    service.configure_provider("fake", {"token": "t"})
    service.set_selection("fake", ["a", "b"])
    return service.refresh()


def import_fake(admin_client: TestClient, source_ids: Sequence[str] = ("a", "b")) -> Any:
    """The same thing over HTTP: connect, choose sources, sync."""
    admin_client.put(f"{ADMIN}/providers/fake/config", json={"config": {"token": "t"}})
    admin_client.put(f"{ADMIN}/providers/fake/selection", json={"source_ids": list(source_ids)})
    return admin_client.post(f"{ADMIN}/refresh").json()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_file=tmp_path / "bridge.json",
        admin_password=ADMIN_PASSWORD,
        public_url="https://checklists.example.com",
    )


#: The suite talks HTTPS because the session cookie is marked Secure, which is
#: what the bridge's only supported deployment needs. Over plain http the client
#: would accept the cookie and then decline to send it back, and every
#: authenticated test would fail with a puzzling 401.
TEST_ORIGIN = "https://testserver"


@pytest.fixture
def client(settings: Settings, service: ChecklistService) -> Any:
    with TestClient(create_app(settings, service), base_url=TEST_ORIGIN) as test_client:
        yield test_client


@pytest.fixture
def admin_client(client: TestClient) -> TestClient:
    response = client.post("/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    # Every later write goes through the cross-origin guard, exactly as the
    # browser's would: the page's own fetches carry this header.
    client.headers["Origin"] = TEST_ORIGIN
    return client


@pytest.fixture
def device_headers(service: ChecklistService) -> dict[str, str]:
    return {"Authorization": f"Bearer {service.device_token}"}


def fake_vikunja(
    routes: Mapping[str, Any],
    *,
    base_url: str = "https://vikunja.example.com",
    token: str = "tk_secret",
) -> VikunjaProvider:
    """Build a VikunjaProvider whose HTTP calls are served from ``routes``.

    ``routes`` maps a request path to either a JSON payload or an
    ``(status_code, payload)`` pair.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        entry = routes.get(request.url.path)
        if entry is None:
            return httpx.Response(404, json={"message": "not found"})
        if callable(entry):
            entry = entry(request)
        status_code, payload = entry if isinstance(entry, tuple) else (200, entry)
        return httpx.Response(status_code, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return VikunjaProvider(base_url, token, client=client)


def fake_trilium(
    routes: Mapping[str, Any],
    *,
    base_url: str = "https://trilium.example.com",
    token: str = "etapi-secret",
    **kwargs: Any,
) -> TriliumProvider:
    """Build a TriliumProvider whose ETAPI calls are served from ``routes``.

    Same convention as ``fake_vikunja``: a path maps to a payload, an
    ``(status_code, payload)`` pair, or a callable taking the request. A payload
    that is a plain string is served as the note content endpoints do, as a body
    rather than JSON.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        entry = routes.get(request.url.path)
        if entry is None:
            return httpx.Response(404, json={"message": "note not found"})
        if callable(entry):
            entry = entry(request)
        status_code, payload = entry if isinstance(entry, tuple) else (200, entry)
        if isinstance(payload, httpx.Response):
            return payload
        if isinstance(payload, str):
            return httpx.Response(status_code, text=payload)
        return httpx.Response(status_code, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return TriliumProvider(base_url, token, client=client, **kwargs)


def page(items: Sequence[Any], *, page_number: int = 1, per_page: int = 100) -> dict[str, Any]:
    """Wrap ``items`` in Vikunja's v2 pagination envelope."""
    return {
        "items": items,
        "total": len(items),
        "page": page_number,
        "per_page": per_page,
        "total_pages": 1,
    }
