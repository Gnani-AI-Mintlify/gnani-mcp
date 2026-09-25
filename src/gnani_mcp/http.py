"""Async HTTP client for the Gnani (Vachana) REST API.

All outbound requests share a single ``httpx.AsyncClient`` instance created
at server startup and closed cleanly during lifespan shutdown.  The client
owns authentication, error mapping, and timeout policy — tool modules never
touch httpx directly.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from gnani_mcp.exceptions import (
    AuthenticationError,
    GnaniAPIError,
    InvalidRequestError,
    RateLimitError,
    ServiceUnavailableError,
)

logger = logging.getLogger("gnani_mcp.http")

# Generous but bounded timeouts: connect quickly, give reads up to 2 min.
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0)

# Error-type string → exception class mapping (from Gnani API error envelope).
_ERROR_TYPE_MAP: dict[str, type[GnaniAPIError]] = {
    "FORBIDDEN": AuthenticationError,
    "INVALID_REQUEST_ERROR": InvalidRequestError,
    "RATE_LIMIT_ERROR": RateLimitError,
    "SERVICE_UNAVAILABLE": ServiceUnavailableError,
}

_STATUS_CODE_MAP: dict[int, type[GnaniAPIError]] = {
    401: AuthenticationError,
    403: AuthenticationError,
    400: InvalidRequestError,
    429: RateLimitError,
    503: ServiceUnavailableError,
}


class GnaniClient:
    """Thin async wrapper around ``httpx`` for the Gnani/Vachana REST API.

    Usage::

        client = GnaniClient(base_url="https://api.vachana.ai", api_key="sk_...")
        json_payload = await client.post_multipart("/stt/v3", data=..., files=...)
        audio_bytes  = await client.post_json_binary("/api/v1/tts/inference", json_body=...)
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
                "or in ~/.gnani/credentials (api_key = sk_...)."
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
        resp = await self._client.post(
            path,
            headers=self._auth_headers(),
            data=data,
            files=files,
        )
        return self._parse_json_response(resp)

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

    # ------------------------------------------------------------------
    # Response parsing & error mapping
    # ------------------------------------------------------------------

    def _parse_json_response(self, resp: httpx.Response) -> dict[str, Any]:
        if not resp.is_success:
            self._raise_from_response(resp)
        return resp.json()

    def _raise_from_response(self, resp: httpx.Response) -> None:
        """Extract error details from the response and raise the appropriate exception."""
        message: str
        error_type: str = "API_ERROR"

        try:
            body = resp.json()
            error_detail = body.get("error", {})
            message = error_detail.get("message") or resp.text or "Unknown error"
            error_type = error_detail.get("type", "API_ERROR")
        except Exception:
            message = resp.text or f"HTTP {resp.status_code}"

        exc_cls = _ERROR_TYPE_MAP.get(error_type) or _STATUS_CODE_MAP.get(resp.status_code, GnaniAPIError)
        raise exc_cls(message, resp.status_code)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()
