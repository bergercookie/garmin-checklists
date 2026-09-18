"""Cross-origin refusal, login throttling and response headers."""

from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from checklists_bridge.service import ChecklistService
from checklists_bridge.web.guard import (
    BASE_LOCKOUT_SECONDS,
    FORGET_AFTER_SECONDS,
    FREE_ATTEMPTS,
    MAX_LOCKOUT_SECONDS,
    SECURITY_HEADERS,
    LoginThrottle,
    client_address,
    is_same_origin,
    request_origin,
)
from conftest import ADMIN_PASSWORD

ORIGIN = "https://checklists.example.com"


def make_request(
    headers: dict[str, str] | None = None,
    *,
    scheme: str = "http",
    client: tuple[str, int] | None = ("10.0.0.1", 1234),
) -> Request:
    raw = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin/refresh",
            "headers": raw,
            "scheme": scheme,
            "server": ("checklists.example.com", 443),
            "query_string": b"",
            "client": client,
        }
    )


def test_the_origin_is_taken_from_the_forwarded_scheme_when_there_is_one() -> None:
    # Behind a proxy uvicorn sees http, so trusting request.url.scheme would
    # compare https pages against an http origin and refuse everything.
    request = make_request({"host": "checklists.example.com", "x-forwarded-proto": "https, http"})
    assert request_origin(request) == ORIGIN


def test_a_request_with_no_host_header_has_no_origin() -> None:
    assert request_origin(make_request({})) == ""


@pytest.mark.parametrize(
    ("headers", "allowed"),
    [
        ({"host": "checklists.example.com", "origin": ORIGIN}, True),
        ({"host": "checklists.example.com", "origin": "https://evil.example"}, False),
        # A sibling host on the same registrable domain is "same-site" as far as
        # a Lax cookie is concerned, which is exactly the gap this closes.
        ({"host": "checklists.example.com", "origin": "https://wiki.example.com"}, False),
        ({"host": "checklists.example.com", "referer": f"{ORIGIN}/page"}, True),
        ({"host": "checklists.example.com", "referer": "https://evil.example/x"}, False),
        # Neither header: not a browser, so not a CSRF vector. curl keeps working.
        ({"host": "checklists.example.com"}, True),
    ],
)
def test_only_our_own_page_may_make_a_state_changing_request(
    headers: dict[str, str], allowed: bool
) -> None:
    request = make_request({**headers, "x-forwarded-proto": "https"})
    assert is_same_origin(request) is allowed


def test_the_configured_public_url_is_also_accepted() -> None:
    request = make_request({"host": "127.0.0.1:8099", "origin": ORIGIN})
    assert is_same_origin(request) is False
    assert is_same_origin(request, ORIGIN) is True


def test_a_referer_without_a_scheme_is_not_treated_as_our_origin() -> None:
    request = make_request({"host": "checklists.example.com", "referer": "/relative"})
    assert is_same_origin(request) is False


def test_the_first_few_wrong_passwords_are_free() -> None:
    throttle = LoginThrottle()
    for _ in range(FREE_ATTEMPTS):
        throttle.record_failure("10.0.0.1")
    assert throttle.locked_for("10.0.0.1") == 0.0


def test_further_failures_lock_the_client_out_for_a_doubling_period() -> None:
    throttle = LoginThrottle()
    for _ in range(FREE_ATTEMPTS + 1):
        throttle.record_failure("10.0.0.1", now=0.0)
    assert throttle.locked_for("10.0.0.1", now=0.0) == BASE_LOCKOUT_SECONDS

    throttle.record_failure("10.0.0.1", now=0.0)
    assert throttle.locked_for("10.0.0.1", now=0.0) == BASE_LOCKOUT_SECONDS * 2

    # The wait shrinks as it is served, and reaches zero.
    assert throttle.locked_for("10.0.0.1", now=BASE_LOCKOUT_SECONDS * 2) == 0.0


def test_the_lockout_stops_doubling_before_it_becomes_a_denial_of_service() -> None:
    throttle = LoginThrottle()
    for _ in range(60):
        throttle.record_failure("10.0.0.1", now=0.0)
    assert throttle.locked_for("10.0.0.1", now=0.0) == MAX_LOCKOUT_SECONDS


def test_one_client_being_locked_out_does_not_affect_another() -> None:
    throttle = LoginThrottle()
    for _ in range(FREE_ATTEMPTS + 3):
        throttle.record_failure("10.0.0.1", now=0.0)
    assert throttle.locked_for("10.0.0.1", now=0.0) > 0
    assert throttle.locked_for("10.0.0.2", now=0.0) == 0.0


def test_signing_in_clears_the_record() -> None:
    throttle = LoginThrottle()
    for _ in range(FREE_ATTEMPTS + 3):
        throttle.record_failure("10.0.0.1", now=0.0)
    throttle.record_success("10.0.0.1")
    assert throttle.locked_for("10.0.0.1", now=0.0) == 0.0


def test_quiet_clients_are_forgotten_so_the_table_cannot_grow_without_bound() -> None:
    throttle = LoginThrottle()
    throttle.record_failure("10.0.0.1", now=0.0)
    assert throttle.locked_for("10.0.0.2", now=FORGET_AFTER_SECONDS + 1) == 0.0
    assert throttle._failures == {}


def test_a_request_with_no_client_is_throttled_under_a_shared_name() -> None:
    assert client_address(make_request({}, client=None)) == "unknown"
    assert client_address(make_request({})) == "10.0.0.1"


def test_the_watch_api_is_exempt_from_the_origin_check(
    client: TestClient, service: ChecklistService
) -> None:
    # The watch sends no Origin and authenticates with a bearer token, which a
    # browser will never attach on another site's behalf.
    assert (
        client.get(
            "/api/v1/watch/lists", headers={"Authorization": f"Bearer {service.device_token}"}
        ).status_code
        == 200
    )


def test_the_openapi_schema_is_not_served(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404


def test_too_many_wrong_passwords_locks_the_client_out(client: TestClient) -> None:
    for _ in range(12):
        client.post("/login", data={"password": "wrong"}, follow_redirects=False)
    locked = client.post("/login", data={"password": "wrong"}, follow_redirects=False)
    assert "locked=" in locked.headers["location"]

    # And the lockout is not a password oracle: the right password waits too.
    correct = client.post("/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False)
    assert "locked=" in correct.headers["location"]
    assert client.get("/login").status_code == 200


def test_the_referrer_policy_does_not_break_our_own_login_form() -> None:
    # Under `no-referrer`, Chrome sends `Origin: null` on a form POST, which the
    # cross-origin check then refuses -- so sign-in was rejected by our own CSRF
    # defence in every real browser, while these httpx-based tests passed
    # because httpx implements no referrer policy at all. `same-origin` keeps
    # the privacy win and keeps same-origin posts identifiable.
    assert SECURITY_HEADERS["Referrer-Policy"] == "same-origin"


def test_an_origin_of_null_is_refused() -> None:
    # Which is what made the above worth pinning: "null" must not be treated as
    # "absent", or the check would pass for exactly the case that broke.
    request = make_request({"host": "checklists.example.com", "origin": "null"})
    assert is_same_origin(request) is False
