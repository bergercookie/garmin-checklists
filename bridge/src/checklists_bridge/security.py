"""Token generation and the signed cookie used by the web UI.

Deliberately tiny and dependency-free: two HMACs and a constant-time compare are
easier to audit than a session framework.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

#: Ambiguous characters are left out so the token is easy to retype by hand.
_TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
#: 12 characters from a 32-symbol alphabet is 60 bits. The token is a bearer
#: credential on an endpoint with no rate limiting, so entropy is the only
#: defence -- but 60 bits is already out of reach of anyone guessing over the
#: internet, and every character beyond that is one more to mistype.
_TOKEN_LENGTH = 12
_TOKEN_GROUP = 4

SESSION_TTL_SECONDS = 30 * 24 * 60 * 60


def new_device_token() -> str:
    """Return a token such as ``K7QF-2M9X-PLDR``."""
    raw = "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LENGTH))
    groups = [raw[i : i + _TOKEN_GROUP] for i in range(0, _TOKEN_LENGTH, _TOKEN_GROUP)]
    return "-".join(groups)


def new_secret() -> str:
    """Return a fresh URL-safe secret used to sign session cookies."""
    return secrets.token_urlsafe(32)


def tokens_match(presented: str, expected: str) -> bool:
    """Constant-time comparison that tolerates missing whitespace and case."""
    return hmac.compare_digest(_normalise(presented), _normalise(expected))


def passwords_match(presented: str, expected: str) -> bool:
    return hmac.compare_digest(presented.encode(), expected.encode())


def _normalise(token: str) -> bytes:
    return token.strip().upper().replace("-", "").replace(" ", "").encode()


def sign_session(secret: str, epoch: int, *, issued_at: float | None = None) -> str:
    """Return ``<expiry>.<epoch>.<signature>`` for a session lasting 30 days.

    ``epoch`` is the server's current session generation. Raising it invalidates
    every cookie ever issued, which is the only revocation this design supports:
    there is no server-side session list, so sessions cannot be dropped one at a
    time. See :meth:`ChecklistService.revoke_sessions`.
    """
    expiry = int((time.time() if issued_at is None else issued_at) + SESSION_TTL_SECONDS)
    payload = f"{expiry}.{epoch}"
    return f"{payload}.{_sign(secret, payload)}"


def verify_session(secret: str, cookie: str, epoch: int, *, now: float | None = None) -> bool:
    """Return True if ``cookie`` is current, correctly signed and unexpired.

    Never raises: the cookie is attacker-controlled, and every malformed shape
    has to come back as a plain False.
    """
    expiry_text, _, rest = cookie.partition(".")
    epoch_text, separator, signature = rest.partition(".")
    if not separator:
        return False
    if not _signatures_match(signature, _sign(secret, f"{expiry_text}.{epoch_text}")):
        return False
    try:
        expiry, presented_epoch = int(expiry_text), int(epoch_text)
    except ValueError:
        return False
    if presented_epoch != epoch:
        return False
    return expiry > (time.time() if now is None else now)


def _signatures_match(presented: str, expected: str) -> bool:
    """Compare in constant time, tolerating whatever bytes arrived in the header.

    `hmac.compare_digest` raises TypeError on strings holding non-ASCII, and
    Starlette decodes headers as latin-1, so one high byte in the cookie would
    otherwise become an unauthenticated 500.
    """
    return hmac.compare_digest(presented.encode("utf-8", "replace"), expected.encode())


def _sign(secret: str, payload: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")
