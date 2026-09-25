"""Gnani API exception hierarchy."""

from __future__ import annotations


class GnaniAPIError(Exception):
    """Base exception for all Gnani API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code

    def __str__(self) -> str:  # pragma: no cover
        if self.status_code is not None:
            return f"[HTTP {self.status_code}] {self.message}"
        return self.message


class AuthenticationError(GnaniAPIError):
    """Raised when the API key is missing, invalid, or lacks permission (HTTP 401/403)."""


class InvalidRequestError(GnaniAPIError):
    """Raised for bad request parameters or unsupported audio format (HTTP 400)."""


class RateLimitError(GnaniAPIError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""


class ServiceUnavailableError(GnaniAPIError):
    """Raised when a downstream service is temporarily unavailable (HTTP 503)."""
