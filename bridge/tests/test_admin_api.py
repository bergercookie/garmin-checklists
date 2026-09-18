from __future__ import annotations

from fastapi.testclient import TestClient

import fakes
from checklists_bridge.providers import REGISTRY
from checklists_bridge.service import ChecklistService
from conftest import ADMIN, import_fake


def test_the_real_registry_offers_every_provider() -> None:
    assert {spec.id for spec in REGISTRY.all()} == {"local", "vikunja", "trilium"}


def test_admin_api_requires_a_session(client: TestClient) -> None:
    assert client.get(f"{ADMIN}/state").status_code == 401


def test_wrong_password_does_not_sign_you_in(client: TestClient) -> None:
    response = client.post("/login", data={"password": "wrong"}, follow_redirects=False)
    assert response.headers["location"] == "/login?error=1"
    assert client.get(f"{ADMIN}/state").status_code == 401


def test_state_describes_providers_and_pairing(
    admin_client: TestClient, service: ChecklistService
) -> None:
    payload = admin_client.get(f"{ADMIN}/state").json()
    assert payload["device_token"] == service.device_token
    assert payload["public_url"] == "https://checklists.example.com"
    assert {provider["id"] for provider in payload["providers"]} == {"local", "fake"}
    local = next(item for item in payload["providers"] if item["id"] == "local")
    assert local["editable"] is True


def test_provider_setup_form_is_described_by_the_backend(admin_client: TestClient) -> None:
    payload = admin_client.get(f"{ADMIN}/state").json()
    fake = next(item for item in payload["providers"] if item["id"] == "fake")
    assert fake["fields"] == [
        {
            "name": "token",
            "label": "Token",
            "kind": "password",
            "required": True,
            "placeholder": "",
            "help": "",
            "default": "",
        }
    ]


def test_onboarding_flow_connect_pick_sync(admin_client: TestClient) -> None:
    connected = admin_client.put(f"{ADMIN}/providers/fake/config", json={"config": {"token": "t"}})
    assert connected.status_code == 200
    assert {source["name"] for source in connected.json()["sources"]} == {"Dive kit", "Travel"}

    sources = admin_client.get(f"{ADMIN}/providers/fake/sources").json()["sources"]
    assert len(sources) == 2

    admin_client.put(f"{ADMIN}/providers/fake/selection", json={"source_ids": ["a"]})
    report = admin_client.post(f"{ADMIN}/refresh").json()
    assert report["ok"] is True
    assert [item["name"] for item in report["checklists"]] == ["Dive kit"]


def test_bad_credentials_surface_as_a_gateway_error(admin_client: TestClient) -> None:
    fakes.FAIL["auth"] = True
    response = admin_client.put(f"{ADMIN}/providers/fake/config", json={"config": {"token": "t"}})
    assert response.status_code == 502


def test_local_checklist_crud(admin_client: TestClient) -> None:
    created = admin_client.post(f"{ADMIN}/local/checklists", json={"name": "Pre-dive"}).json()

    admin_client.put(
        f"{ADMIN}/local/checklists/{created['id']}",
        json={"name": "Pre-dive checks", "items": ["Air", "Weights", ""]},
    )
    state = admin_client.get(f"{ADMIN}/state").json()
    assert state["local_checklists"] == [
        {"id": created["id"], "name": "Pre-dive checks", "items": ["Air", "Weights"]}
    ]

    assert admin_client.delete(f"{ADMIN}/local/checklists/{created['id']}").status_code == 204
    assert admin_client.get(f"{ADMIN}/state").json()["local_checklists"] == []


def test_editing_an_unknown_local_checklist_is_404(admin_client: TestClient) -> None:
    response = admin_client.put(f"{ADMIN}/local/checklists/nope", json={"items": []})
    assert response.status_code == 404


def test_blank_checklist_name_is_rejected(admin_client: TestClient) -> None:
    response = admin_client.post(f"{ADMIN}/local/checklists", json={"name": "  "})
    assert response.status_code == 400


def test_rotating_the_device_token_from_the_ui(
    admin_client: TestClient, service: ChecklistService
) -> None:
    before = service.device_token
    issued = admin_client.post(f"{ADMIN}/device-token").json()["device_token"]
    assert issued != before
    assert issued == service.device_token


def test_health_endpoint_needs_no_auth(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"


def test_index_redirects_to_login_when_signed_out(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_index_renders_once_signed_in(admin_client: TestClient) -> None:
    assert "Device token" in admin_client.get("/").text


def test_logout_clears_the_session(admin_client: TestClient) -> None:
    response = admin_client.post("/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert admin_client.get(f"{ADMIN}/state").status_code == 401


def test_the_login_page_reports_a_bad_password(client: TestClient) -> None:
    assert "Wrong password" in client.get("/login?error=1").text


def test_disconnecting_a_provider_drops_its_checklists(admin_client: TestClient) -> None:
    import_fake(admin_client, ["a"])

    assert admin_client.delete(f"{ADMIN}/providers/fake/config").status_code == 204
    state = admin_client.get(f"{ADMIN}/state").json()
    assert state["snapshot"] == []
    assert next(p for p in state["providers"] if p["id"] == "fake")["configured"] is False


def test_unknown_providers_are_rejected_on_every_route(admin_client: TestClient) -> None:
    assert admin_client.get(f"{ADMIN}/providers/nope/sources").status_code == 502
    assert (
        admin_client.put(f"{ADMIN}/providers/nope/config", json={"config": {}}).status_code == 502
    )
    assert (
        admin_client.put(f"{ADMIN}/providers/nope/selection", json={"source_ids": []}).status_code
        == 502
    )
    assert admin_client.delete(f"{ADMIN}/providers/nope/config").status_code == 502


def test_renaming_a_local_checklist_keeps_its_items(admin_client: TestClient) -> None:
    created = admin_client.post(f"{ADMIN}/local/checklists", json={"name": "Kit"}).json()
    admin_client.put(f"{ADMIN}/local/checklists/{created['id']}", json={"items": ["Mask"]})
    admin_client.put(f"{ADMIN}/local/checklists/{created['id']}", json={"name": "Dive kit"})

    state = admin_client.get(f"{ADMIN}/state").json()
    assert state["local_checklists"] == [
        {"id": created["id"], "name": "Dive kit", "items": ["Mask"]}
    ]


def test_deleting_an_unknown_local_checklist_is_404(admin_client: TestClient) -> None:
    assert admin_client.delete(f"{ADMIN}/local/checklists/nope").status_code == 404


def test_refresh_reports_provider_failures(admin_client: TestClient) -> None:
    # Deliberately not import_fake: that syncs first, and this covers a source
    # failing before it has ever been fetched, so there is nothing to fall back
    # to.
    admin_client.put(f"{ADMIN}/providers/fake/config", json={"config": {"token": "t"}})
    admin_client.put(f"{ADMIN}/providers/fake/selection", json={"source_ids": ["a"]})
    fakes.FAIL["auth"] = True

    report = admin_client.post(f"{ADMIN}/refresh").json()
    assert report["ok"] is False
    assert report["errors"]


def test_a_cross_origin_write_is_refused_even_with_a_valid_session(
    admin_client: TestClient,
) -> None:
    # The session cookie is SameSite=lax, which stops a cross-*site* form post
    # but not one from a sibling host on the same registrable domain -- a normal
    # homelab layout. These two routes take no body, so they would otherwise be
    # reachable from a plain auto-submitting form.
    refused = admin_client.post(
        f"{ADMIN}/device-token", headers={"Origin": "https://wiki.example.com"}
    )
    assert refused.status_code == 403
    assert refused.json()["detail"] == "cross-origin request refused"


def test_a_cross_origin_read_is_still_allowed(admin_client: TestClient) -> None:
    # GET changes nothing, and refusing it would break ordinary navigation.
    allowed = admin_client.get(f"{ADMIN}/state", headers={"Origin": "https://wiki.example.com"})
    assert allowed.status_code == 200


def test_revoking_sessions_signs_this_browser_out_too(admin_client: TestClient) -> None:
    assert admin_client.get(f"{ADMIN}/state").status_code == 200
    assert admin_client.post(f"{ADMIN}/sessions/revoke").status_code == 204
    assert admin_client.get(f"{ADMIN}/state").status_code == 401


def test_a_revoked_session_cannot_be_replayed(client: TestClient, admin_client: TestClient) -> None:
    stolen = dict(admin_client.cookies)
    admin_client.post(f"{ADMIN}/sessions/revoke")
    client.cookies.update(stolen)
    assert client.get(f"{ADMIN}/state").status_code == 401


def test_admin_responses_are_not_cacheable_and_carry_security_headers(
    admin_client: TestClient,
) -> None:
    # The state response contains the device token.
    response = admin_client.get(f"{ADMIN}/state")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]


def test_undeclared_config_keys_are_dropped_rather_than_stored(
    admin_client: TestClient, service: ChecklistService
) -> None:
    # `client` is the provider's HTTP client seam. Posting it used to replace the
    # client with a string and turn every later request into a 500.
    admin_client.put(
        f"{ADMIN}/providers/vikunja/config",
        json={
            "config": {"base_url": "https://vikunja.example.com", "token": "tk_x", "client": "x"}
        },
    )
    saved = service._database.read().providers.get("vikunja")
    assert saved is None or "client" not in saved.config
