from __future__ import annotations

import time

from checklists_bridge.security import (
    SESSION_TTL_SECONDS,
    new_device_token,
    new_secret,
    passwords_match,
    sign_session,
    tokens_match,
    verify_session,
)


def test_device_tokens_are_grouped_and_unambiguous() -> None:
    token = new_device_token()
    assert len(token) == 14  # 12 characters in groups of four
    assert token.count("-") == 2
    assert not set(token) & set("OI01")


def test_tokens_match_ignores_case_and_grouping() -> None:
    assert tokens_match("k7qf2m9xpldr", "K7QF-2M9X-PLDR")
    assert not tokens_match("K7QF-2M9X-PLDS", "K7QF-2M9X-PLDR")


def test_passwords_match_is_exact() -> None:
    assert passwords_match("hunter2", "hunter2")
    assert not passwords_match("Hunter2", "hunter2")


def test_session_cookie_round_trip() -> None:
    secret = new_secret()
    assert verify_session(secret, sign_session(secret, 0), 0)


def test_session_cookie_rejects_other_secrets_and_tampering() -> None:
    cookie = sign_session(new_secret(), 0)
    assert not verify_session(new_secret(), cookie, 0)
    assert not verify_session(new_secret(), "garbage", 0)
    assert not verify_session(new_secret(), "123.abc", 0)


def test_session_cookie_expires() -> None:
    secret = new_secret()
    cookie = sign_session(secret, 0, issued_at=time.time() - SESSION_TTL_SECONDS - 10)
    assert not verify_session(secret, cookie, 0)


def test_session_cookie_rejects_a_signed_but_non_numeric_expiry() -> None:
    # Defensive: the signer never produces this, but a bad cookie must not raise.
    from checklists_bridge.security import _sign

    secret = new_secret()
    assert not verify_session(secret, f"soon.0.{_sign(secret, 'soon.0')}", 0)


def test_raising_the_epoch_invalidates_every_cookie_ever_issued() -> None:
    # The only revocation this design has: there is no server-side session list,
    # so one browser cannot be signed out without signing out the rest.
    secret = new_secret()
    cookie = sign_session(secret, 7)
    assert verify_session(secret, cookie, 7)
    assert not verify_session(secret, cookie, 8)


def test_a_cookie_of_arbitrary_bytes_is_refused_rather_than_raising() -> None:
    # Starlette decodes headers as latin-1, so a single high byte reaches this
    # unescorted. `hmac.compare_digest` raises TypeError on non-ASCII str, which
    # would turn an attacker-controlled cookie into an unauthenticated 500.
    secret = new_secret()
    for cookie in ("1.0.\xe9", "\xff", "1.\u20ac.sig", "1.0."):
        assert verify_session(secret, cookie, 0) is False
