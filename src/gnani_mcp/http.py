"""Async HTTP client for the Gnani (Vachana) REST API.

All outbound requests share a single ``httpx.AsyncClient`` instance created
at server startup and closed cleanly during lifespan shutdown.  The client
owns authentication, error mapping, and timeout policy — tool modules never
touch httpx directly.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
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

# HTTP 429 handling — the API asks clients to "wait and retry with backoff".
# Rate-limited requests are rejected before any work is done, so retrying every
# method (including POST) is safe.
_MAX_RATE_LIMIT_RETRIES = 5
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 10.0

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

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        max_retries: int = _MAX_RATE_LIMIT_RETRIES,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._max_retries = max_retries
        self._sleep = sleep
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

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send a request, retrying HTTP 429 responses with exponential backoff.

        Honours ``Retry-After`` (seconds) when present. Any file objects in
        ``files`` are rewound before each retry so uploads are resent in full.
        """
        attempt = 0
        while True:
            resp = await self._client.request(method, path, **kwargs)
            if resp.status_code != 429 or attempt >= self._max_retries:
                return resp
            delay = self._retry_delay(resp, attempt)
            logger.warning(
                "HTTP 429 from %s %s — retrying in %.1fs (%d/%d)",
                method, path, delay, attempt + 1, self._max_retries,
            )
            await self._sleep(delay)
            attempt += 1
            self._rewind_files(kwargs.get("files"))

    @staticmethod
    def _retry_delay(resp: httpx.Response, attempt: int) -> float:
        retry_after = resp.headers.get("retry-after")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 60.0)
            except ValueError:
                pass
        backoff = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
        return backoff + random.uniform(0, backoff / 4)  # noqa: S311 — jitter, not security

    @staticmethod
    def _rewind_files(files: dict[str, Any] | None) -> None:
        for value in (files or {}).values():
            fh = value[1] if isinstance(value, tuple) and len(value) > 1 else value
            if hasattr(fh, "seek"):
                fh.seek(0)

    async def post_multipart(
        self,
        path: str,
        *,
        data: dict[str, Any],
        files: dict[str, Any],
    ) -> dict[str, Any]:
        """POST multipart/form-data; parse and return the JSON response body."""
        resp = await self._request(
            "POST",
            path,
            headers=self._auth_headers(),
            data=data,
            files=files,
        )
        return self._parse_json_response(resp)

    async def post_json(
        self,
        path: str,
        *,
        json_body: dict[str, Any],
    ) -> dict[str, Any]:
        """POST application/json; parse and return the JSON response body."""
        resp = await self._request(
            "POST",
            path,
            headers={**self._auth_headers(), "Content-Type": "application/json"},
            json=json_body,
        )
        return self._parse_json_response(resp)

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET request; parse and return the JSON response body."""
        resp = await self._request(
            "GET",
            path,
            headers=self._auth_headers(),
            params=params,
        )
        return self._parse_json_response(resp)

    async def post_json_binary(
        self,
        path: str,
        *,
        json_body: dict[str, Any],
    ) -> bytes:
        """POST application/json; return raw binary response content (audio bytes)."""
        resp = await self._request(
            "POST",
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
        """Extract error details from the response and raise the appropriate exception.

        Handles two error envelope shapes used by different Gnani API endpoints:

        Shape A (STT / TTS):
            {"success": false, "error": {"type": "...", "message": "..."}}

        Shape B (Voice Clone):
            {"detail": {"error_code": "...", "message": "...", "status_code": ...}}
        """
        message: str
        error_type: str = "API_ERROR"

        try:
            body = resp.json()

            # Shape A — standard STT/TTS envelope
            if "error" in body:
                error_detail = body["error"]
                message = error_detail.get("message") or resp.text or "Unknown error"
                error_type = error_detail.get("type", "API_ERROR")

            # Shape B — Voice Clone / alternate envelope
            elif "detail" in body:
                detail = body["detail"]
                if isinstance(detail, dict):
                    message = detail.get("message") or resp.text or "Unknown error"
                    # Map error_code → error_type
                    error_type = {
                        "RATE_LIMITED": "RATE_LIMIT_ERROR",
                        "UNAUTHORIZED": "FORBIDDEN",
                        "FORBIDDEN": "FORBIDDEN",
                        "BAD_REQUEST": "INVALID_REQUEST_ERROR",
                    }.get(detail.get("error_code", ""), "API_ERROR")
                else:
                    message = str(detail) or resp.text or "Unknown error"

            else:
                message = resp.text or f"HTTP {resp.status_code}"

        except Exception:
            message = resp.text or f"HTTP {resp.status_code}"

        exc_cls = _ERROR_TYPE_MAP.get(error_type) or _STATUS_CODE_MAP.get(resp.status_code, GnaniAPIError)
        raise exc_cls(message, resp.status_code)

    async def get_presigned(self, url: str) -> dict[str, Any]:
        """GET a pre-signed URL (no auth header). Used for transcript downloads."""
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
            resp = await c.get(url)
        if not resp.is_success:
            raise GnaniAPIError(
                f"Failed to download transcript URL (HTTP {resp.status_code}): {resp.text[:200]}",
                resp.status_code,
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()
