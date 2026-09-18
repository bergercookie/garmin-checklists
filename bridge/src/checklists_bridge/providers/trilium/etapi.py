"""The two-and-a-bit ETAPI routes this provider needs, and nothing else.

Trilium's External API lives under ``/etapi`` and authenticates with a bare
token in the Authorization header -- not ``Bearer <token>``, which only newer
versions accept. The bare form works everywhere, so that is what is sent.

    GET {base}/etapi/notes?search=…&limit=…&orderBy=title
    GET {base}/etapi/notes/{noteId}
    GET {base}/etapi/notes/{noteId}/content

The first two answer JSON; the third answers the note's raw content, which for a
text note is HTML. That is why `content()` returns text rather than a mapping.
"""

from __future__ import annotations

from typing import Any

import httpx

from checklists_bridge.providers.base import (
    ProviderAuthError,
    ProviderUnavailableError,
    SourceNotFoundError,
)

API_PREFIX = "/etapi"
REQUEST_TIMEOUT = 15.0


def _is_trilium_error(response: httpx.Response) -> bool:
    """Did this refusal come from the ETAPI itself, or from in front of it?

    Trilium answers a bad token with JSON carrying a `code`, and does it with
    401 -- never 403. Anything else refusing the request is a hop in between:
    an SSO proxy, an access policy, a WAF. Telling the two apart is the whole
    difference between "your token is wrong" and "your token never arrived".
    """
    if "application/json" not in response.headers.get("content-type", ""):
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    return isinstance(payload, dict) and "code" in payload


def _refusal(response: httpx.Response, url: str) -> str:
    if _is_trilium_error(response):
        return (
            f"Trilium rejected the ETAPI token (HTTP {response.status_code}). If the token is "
            "right and Trilium sits behind a reverse proxy, check that it passes the "
            "Authorization header through rather than consuming it."
        )
    kind = response.headers.get("content-type", "no content type").split(";")[0]
    return (
        f"{url} was refused with HTTP {response.status_code} by something in front of Trilium "
        f"(the reply was {kind}, not a Trilium error). Trilium's own ETAPI answers 401 with "
        "JSON for a bad token, so this is an SSO proxy, an access policy or a WAF."
    )


class Etapi:
    """A thin, typed wrapper over the handful of routes we use."""

    def __init__(self, base_url: str, token: str, *, client: httpx.Client | None = None) -> None:
        self._base_url = base_url
        self._token = token.strip()
        self._client = client or httpx.Client(timeout=REQUEST_TIMEOUT)

    def close(self) -> None:
        self._client.close()

    def search(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        """Notes matching a Trilium search expression, newest API shape first."""
        payload = self._get(
            "/notes",
            params={
                "search": query,
                "limit": limit,
                # Stable order, so the import picker does not reshuffle itself
                # between visits.
                "orderBy": "title",
                "orderDirection": "asc",
            },
        )
        results = payload.get("results")
        if not isinstance(results, list):
            raise ProviderUnavailableError(
                "Trilium's search returned no 'results' list; is that really an ETAPI endpoint?"
            )
        return [item for item in results if isinstance(item, dict)]

    def note(self, note_id: str) -> dict[str, Any]:
        return self._get(f"/notes/{note_id}")

    def content(self, note_id: str) -> str:
        """The note's body. Text notes give HTML; code notes give plain text."""
        return self._request(f"/notes/{note_id}/content").text

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._request(path, params)
        try:
            payload = response.json()
        except ValueError as error:
            raise ProviderUnavailableError(f"Trilium did not answer {path} with JSON") from error
        if not isinstance(payload, dict):
            raise ProviderUnavailableError(f"Trilium answered {path} with {type(payload).__name__}")
        return payload

    def _request(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self._base_url}{API_PREFIX}{path}"
        try:
            response = self._client.get(
                url,
                params=dict(params or {}),
                # A bare token, not "Bearer <token>": Trilium only started
                # accepting the Bearer spelling in 0.93.
                headers={"Authorization": self._token},
            )
        except httpx.HTTPError as error:
            raise ProviderUnavailableError(f"could not reach Trilium at {url}: {error}") from error

        if response.status_code in (401, 403):
            raise ProviderAuthError(_refusal(response, url))
        if response.status_code == 404:
            raise SourceNotFoundError(f"Trilium has nothing at {path}")
        if response.status_code >= 400:
            raise ProviderUnavailableError(
                f"Trilium returned HTTP {response.status_code} for {path}"
            )
        return response
