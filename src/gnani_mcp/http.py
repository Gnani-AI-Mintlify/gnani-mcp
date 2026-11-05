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
    GnaniConnectionError,
    InvalidRequestError,
    RateLimitError,
    ServiceUnavailableError,
)

logger = logging.getLogger("gnani_mcp.http")

# ``X-Source`` tells the backend which channel is calling, so usage and billing are
# attributed to this MCP server. Other channels send "playground", "livekit", "pipecat";
# never use "batch" — the STT service treats it as internal and skips billing.
SOURCE = "mcp"

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


# Voice-clone style ``detail.error_code`` values that map onto a typed exception.
_DETAIL_CODE_TO_TYPE = {
    "RATE_LIMITED": "RATE_LIMIT_ERROR",
    "UNAUTHORIZED": "FORBIDDEN",
    "FORBIDDEN": "FORBIDDEN",
    "BAD_REQUEST": "INVALID_REQUEST_ERROR",
}

# FastAPI prefixes validation-error locations with where the field was found.
_LOC_PREFIXES = frozenset({"body", "query", "path", "header", "cookie"})


def _first_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _format_validation_errors(items: list[Any]) -> str:
    """``[{'loc': ['path', 'job_id'], 'msg': 'bad uuid'}]`` -> ``job_id: bad uuid``."""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        loc = [str(x) for x in (item.get("loc") or [])]
        if loc and loc[0] in _LOC_PREFIXES:
            loc = loc[1:]
        msg = _first_text(item.get("msg")) or "invalid value"
        parts.append(f"{'.'.join(loc)}: {msg}" if loc else msg)
    return "; ".join(parts)


def parse_error_response(resp: httpx.Response) -> tuple[str, str | None, str]:
    """Return ``(message, api_error_code, error_type)`` for a failed response.

    The API does not use one error format.  Recognised shapes:

    * ``{"error": {"type", "message"}}``                      — STT / TTS envelope
    * ``{"error": "JOB_NOT_FOUND", "message": "..."}``        — batch API
    * ``{"detail": {"error_code", "message"}}``               — voice clone
    * ``{"detail": [{"loc", "msg"}, ...]}``                   — request validation (HTTP 422)
    * ``{"detail": "text"}``
    * ``{"success": false, "message": "...", "status_code"}`` — TTS / voice clone
    * plain text (or nothing)

    Anything else falls back to the raw response text, so no information is lost.
    ``error_type`` is the envelope's error type (``"API_ERROR"`` when it has none).
    """
    text = (resp.text or "").strip()
    fallback = text or resp.reason_phrase or f"HTTP {resp.status_code}"
    try:
        body = resp.json()
    except ValueError:
        return fallback, None, "API_ERROR"
    if not isinstance(body, dict):
        return fallback, None, "API_ERROR"

    error, detail = body.get("error"), body.get("detail")
    if isinstance(error, dict):
        return _first_text(error.get("message")) or fallback, None, str(error.get("type") or "API_ERROR")
    if isinstance(error, str):
        return _first_text(body.get("message")) or error, error, "API_ERROR"
    if isinstance(detail, dict):
        code = _first_text(detail.get("error_code"))
        return (
            _first_text(detail.get("message")) or fallback,
            code,
            _DETAIL_CODE_TO_TYPE.get(code or "", "API_ERROR"),
        )
    if isinstance(detail, list):
        return _format_validation_errors(detail) or fallback, None, "API_ERROR"
    if _first_text(detail):
        return _first_text(detail) or fallback, None, "API_ERROR"
    return _first_text(body.get("message")) or fallback, None, "API_ERROR"


def connection_error(exc: httpx.TransportError, method: str, target: str) -> GnaniConnectionError:
    """Turn a low-level network failure into a message that says what happened and what to do.

    httpx's own text is often empty (timeouts) or cryptic, and gives no hint of whether
    repeating the request is safe.
    """
    if isinstance(exc, httpx.ConnectTimeout):
        what = f"timed out connecting to the Gnani API (>{_TIMEOUT.connect:g}s)"
    elif isinstance(exc, httpx.PoolTimeout):
        what = "too many requests are already in flight (connection pool exhausted)"
    elif isinstance(exc, httpx.ReadTimeout):
        what = f"the Gnani API did not respond within {_TIMEOUT.read:g}s"
    elif isinstance(exc, httpx.WriteTimeout):
        what = f"timed out while sending the request (>{_TIMEOUT.write:g}s)"
    elif isinstance(exc, httpx.ConnectError):
        what = "could not connect to the Gnani API (network or DNS problem)"
    elif isinstance(exc, httpx.RemoteProtocolError):
        what = "the Gnani API closed the connection without a response"
    elif isinstance(exc, (httpx.ReadError, httpx.WriteError)):
        what = "the connection to the Gnani API was lost"
    else:
        what = f"network error ({type(exc).__name__})"
    detail = str(exc).strip().rstrip(".")
    if detail and detail.lower() not in what.lower():
        what += f" [{detail}]"

    not_sent = isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout))
    if not_sent:
        advice = "The request was not sent, so it is safe to retry."
    elif method.upper() in ("GET", "HEAD"):
        advice = "This is a read-only request, so it is safe to retry."
    else:
        advice = (
            "The server may already have received and processed it. Check the result "
            "(for example list existing jobs) before repeating a request that creates something."
        )
    return GnaniConnectionError(f"{method.upper()} {target}: {what}. {advice}", request_not_sent=not_sent)


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
        return {"X-API-Key-ID": self._api_key, "X-Source": SOURCE}

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
            try:
                resp = await self._client.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                raise connection_error(exc, method, path) from exc
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
        """Raise the right exception for a non-2xx *resp* (see :func:`parse_error_response`)."""
        message, code, error_type = parse_error_response(resp)
        exc_cls = _ERROR_TYPE_MAP.get(error_type) or _STATUS_CODE_MAP.get(resp.status_code, GnaniAPIError)
        raise exc_cls(message, resp.status_code, code=code)

    async def get_presigned(self, url: str) -> dict[str, Any]:
        """GET a pre-signed URL (no auth header). Used for transcript downloads."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
                resp = await c.get(url)
        except httpx.TransportError as exc:
            # The URL is signed, so name the step rather than echo it.
            raise connection_error(exc, "GET", "transcript download") from exc
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
