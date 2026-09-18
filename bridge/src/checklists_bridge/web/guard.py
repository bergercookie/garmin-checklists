"""Three small defences for the web UI: origin checks, throttling, headers.

Hand-written rather than pulled from a framework because each is a dozen lines
and the whole point is that you can read them and believe them.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request, Response
from fastapi.responses import JSONResponse

#: Methods that cannot change anything, so they need no origin check.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

#: Paths exempt from the origin check: the watch authenticates with a bearer
#: token, which a browser will not attach on anyone else's behalf.
BEARER_PREFIX = "/api/v1/watch"

#: Wrong passwords tolerated before a client is made to wait.
FREE_ATTEMPTS = 5
#: First lockout, doubling with each further failure.
BASE_LOCKOUT_SECONDS = 15.0
MAX_LOCKOUT_SECONDS = 900.0
#: Clients are forgotten once quiet for this long, so the table cannot grow.
FORGET_AFTER_SECONDS = 3600.0

Handler = Callable[[Request], Awaitable[Response]]


def request_origin(request: Request) -> str:
    """The origin this request was addressed to, as a browser would compute it.

    Taken from the Host header rather than from configuration, so it is right
    behind a reverse proxy without anybody having to say so.
    """
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    scheme = forwarded or request.url.scheme
    host = request.headers.get("host", "")
    return f"{scheme}://{host}" if host else ""


def is_same_origin(request: Request, extra_allowed: str = "") -> bool:
    """True if a state-changing request came from our own page.

    A browser sets Origin on every cross-site POST and will not let a page forge
    it, which is what makes this a CSRF defence. Requests with neither Origin nor
    Referer are allowed through: they cannot come from a browser form, and
    blocking them would break `curl` against the admin API for no gain.
    """
    stated = request.headers.get("origin", "")
    if not stated:
        referer = request.headers.get("referer", "")
        if not referer:
            return True
        parts = urlsplit(referer)
        stated = f"{parts.scheme}://{parts.netloc}" if parts.scheme else ""

    allowed = {request_origin(request)}
    if extra_allowed:
        parts = urlsplit(extra_allowed)
        allowed.add(f"{parts.scheme}://{parts.netloc}")
    return stated in allowed


class LoginThrottle:
    """Per-client backoff for password guessing.

    In-process and per-worker on purpose: a dependency-free dictionary is enough
    for a single-user service, and the failure mode of getting it wrong is an
    attacker gaining a few extra guesses, not a breach.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failures: dict[str, tuple[int, float]] = {}

    def locked_for(self, client: str, *, now: float | None = None) -> float:
        """Seconds the client must wait, or 0.0 if it may try."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._forget_quiet_clients(moment)
            count, last = self._failures.get(client, (0, 0.0))
            if count <= FREE_ATTEMPTS:
                return 0.0
            remaining = last + self._lockout(count) - moment
            return max(remaining, 0.0)

    def record_failure(self, client: str, *, now: float | None = None) -> None:
        moment = time.monotonic() if now is None else now
        with self._lock:
            count, _ = self._failures.get(client, (0, 0.0))
            self._failures[client] = (count + 1, moment)

    def record_success(self, client: str) -> None:
        with self._lock:
            self._failures.pop(client, None)

    @staticmethod
    def _lockout(count: int) -> float:
        doublings = count - FREE_ATTEMPTS - 1
        return float(min(BASE_LOCKOUT_SECONDS * (2.0**doublings), MAX_LOCKOUT_SECONDS))

    def _forget_quiet_clients(self, now: float) -> None:
        stale = [
            client
            for client, (_, last) in self._failures.items()
            if now - last > FORGET_AFTER_SECONDS
        ]
        for client in stale:
            del self._failures[client]


def client_address(request: Request) -> str:
    """Who to throttle. Correct behind a proxy only if uvicorn trusts it."""
    return request.client.host if request.client else "unknown"


#: Locked down because the UI loads nothing from anywhere else. If a future page
#: needs a CDN, relax it here rather than dropping the header.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

#: `same-origin`, not `no-referrer`, and the difference is load-bearing: under
#: `no-referrer` Chrome sends `Origin: null` on a form POST, which the check
#: above then refuses -- so the sign-in form was rejected by our own CSRF
#: defence in every real browser, while httpx-based tests passed. This keeps the
#: privacy win (nothing leaks to other sites) and keeps same-origin posts
#: identifiable.
REFERRER_POLICY = "same-origin"

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": REFERRER_POLICY,
    "X-Frame-Options": "DENY",
}


async def apply_guards(request: Request, call_next: Handler, public_url: str = "") -> Response:
    """Reject cross-origin writes, then label every response."""
    if (
        request.method not in SAFE_METHODS
        and not request.url.path.startswith(BEARER_PREFIX)
        and not is_same_origin(request, public_url)
    ):
        return JSONResponse(
            status_code=403,
            content={"detail": "cross-origin request refused"},
            headers=SECURITY_HEADERS,
        )

    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    # The admin API hands out the device token; nothing should cache that.
    if request.url.path.startswith("/api/v1/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response
