"""Async HTTP client for the Gnani (Vachana) REST API.

All outbound requests share a single ``httpx.AsyncClient`` instance created at
server startup and closed cleanly during lifespan shutdown.  The client owns
authentication, error mapping, and timeout policy — tool modules never touch
httpx directly.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from gnani_mcp.exceptions import AuthenticationError
from gnani_mcp.http.errors import raise_from_response

logger = logging.getLogger("gnani_mcp.http")

# Generous but bounded: connect quickly, give reads up to 2 minutes.
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)


class GnaniClient:
    """Thin async wrapper around ``httpx`` for the Gnani / Vachana REST API.

    Usage::

        client = GnaniClient(base_url="https://api.vachana.ai", api_key="vach_...")
        payload  = await client.post_multipart("/stt/v3", data=..., files=...)
        audio    = await client.post_json_binary("/api/v1/tts/inference", json_body=...)
        await client.aclose()
    """

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=_TIMEOUT,
            follow_redirects=True,
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def set_api_key(self, api_key: str) -> None:
        """Update the API key at runtime (e.g. after client-side elicitation)."""
        self._api_key = api_key

    def _auth_headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AuthenticationError(
                "GNANI_API_KEY is not configured. "
                "Set it via the GNANI_API_KEY environment variable "
                "or in ~/.gnani/credentials (api_key = vach_...)."
            )
        return {"X-API-Key-ID": self._api_key}

    # ------------------------------------------------------------------
    # Request helpers
    # ------------------------------------------------------------------

    async def post_multipart(
        self,
        path: str,
        *,
        data: dict[str, Any],
        files: dict[str, Any],
    ) -> dict[str, Any]:
        """POST multipart/form-data; parse and return the JSON response body."""
        resp = await self._client.post(path, headers=self._auth_headers(), data=data, files=files)
        return self._parse_json(resp)

    async def post_json(
        self,
        path: str,
        *,
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        """POST application/json; parse and return the JSON response body."""
        resp = await self._client.post(
            path,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json=json_body,
        )
        return self._parse_json(resp)

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET request; parse and return the JSON response body."""
        resp = await self._client.get(path, headers=self._auth_headers(), params=params)
        return self._parse_json(resp)

    async def post_json_binary(
        self,
        path: str,
        *,
        json_body: dict[str, Any],
    ) -> bytes:
        """POST application/json; return raw binary response content (audio bytes)."""
        resp = await self._client.post(
            path,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json=json_body,
        )
        if not resp.is_success:
            self._raise_from_response(resp)
        return resp.content

    async def get_presigned(self, url: str) -> dict[str, Any]:
        """GET a pre-signed URL (no auth header).  Used for transcript downloads."""
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
            resp = await c.get(url)
        if not resp.is_success:
            from gnani_mcp.exceptions import GnaniAPIError

            raise GnaniAPIError(
                f"Failed to download transcript URL (HTTP {resp.status_code}): {resp.text[:200]}",
                resp.status_code,
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_json(self, resp: httpx.Response) -> dict[str, Any]:
        if not resp.is_success:
            self._raise_from_response(resp)
        return resp.json()

    def _raise_from_response(self, resp: httpx.Response) -> None:
        """Delegate to the module-level error mapper in :mod:`gnani_mcp.http.errors`."""
        raise_from_response(resp)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()
