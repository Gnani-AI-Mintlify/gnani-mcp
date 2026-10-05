"""Error mapping for Gnani API responses.

Gnani uses two different error envelope shapes depending on the endpoint:

Shape A — STT / TTS:
    {"success": false, "error": {"type": "RATE_LIMIT_ERROR", "message": "..."}}

Shape B — Voice Clone:
    {"detail": {"error_code": "RATE_LIMITED", "message": "...", "status_code": 429}}

``raise_from_response`` handles both shapes and maps them to the appropriate
:mod:`gnani_mcp.exceptions` subclass.
"""

from __future__ import annotations

import httpx

from gnani_mcp.exceptions import (
    AuthenticationError,
    GnaniAPIError,
    InvalidRequestError,
    RateLimitError,
    ServiceUnavailableError,
)

# error.type (Shape A) → exception class
_ERROR_TYPE_MAP: dict[str, type[GnaniAPIError]] = {
    "FORBIDDEN": AuthenticationError,
    "INVALID_REQUEST_ERROR": InvalidRequestError,
    "RATE_LIMIT_ERROR": RateLimitError,
    "SERVICE_UNAVAILABLE": ServiceUnavailableError,
}

# HTTP status code → exception class (fallback when no body is available)
_STATUS_CODE_MAP: dict[int, type[GnaniAPIError]] = {
    401: AuthenticationError,
    403: AuthenticationError,
    400: InvalidRequestError,
    429: RateLimitError,
    503: ServiceUnavailableError,
}

# detail.error_code (Shape B) → canonical error_type string
_VC_ERROR_CODE_MAP: dict[str, str] = {
    "RATE_LIMITED": "RATE_LIMIT_ERROR",
    "UNAUTHORIZED": "FORBIDDEN",
    "FORBIDDEN": "FORBIDDEN",
    "BAD_REQUEST": "INVALID_REQUEST_ERROR",
}


def raise_from_response(resp: httpx.Response) -> None:
    """Extract error details from a non-2xx response and raise the right exception.

    Always raises; never returns normally.
    """
    message: str
    error_type: str = "API_ERROR"

    try:
        body = resp.json()

        if "error" in body:
            # Shape A — standard STT / TTS envelope
            error_detail = body["error"]
            message = error_detail.get("message") or resp.text or "Unknown error"
            error_type = error_detail.get("type", "API_ERROR")

        elif "detail" in body:
            # Shape B — Voice Clone / alternate envelope
            detail = body["detail"]
            if isinstance(detail, dict):
                message = detail.get("message") or resp.text or "Unknown error"
                error_type = _VC_ERROR_CODE_MAP.get(detail.get("error_code", ""), "API_ERROR")
            else:
                message = str(detail) or resp.text or "Unknown error"

        else:
            message = resp.text or f"HTTP {resp.status_code}"

    except Exception:  # noqa: BLE001
        message = resp.text or f"HTTP {resp.status_code}"

    exc_cls = _ERROR_TYPE_MAP.get(error_type) or _STATUS_CODE_MAP.get(resp.status_code, GnaniAPIError)
    raise exc_cls(message, resp.status_code)
