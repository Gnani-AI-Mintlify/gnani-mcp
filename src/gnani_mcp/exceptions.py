"""Gnani API exception hierarchy."""

from __future__ import annotations


class GnaniAPIError(Exception):
    """Base exception for all Gnani API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        #: The API's own machine-readable error code (e.g. ``JOB_NOT_FOUND``), when it sent one.
        self.code = code

    def __str__(self) -> str:  # pragma: no cover
        if self.status_code is not None:
            tag = f"HTTP {self.status_code}" + (f" {self.code}" if self.code else "")
            return f"[{tag}] {self.message}"
        return self.message


class AuthenticationError(GnaniAPIError):
    """Raised when the API key is missing, invalid, or lacks permission (HTTP 401/403)."""


class InvalidRequestError(GnaniAPIError):
    """Raised for bad request parameters or unsupported audio format (HTTP 400)."""


class RateLimitError(GnaniAPIError):
    """Raised when the API rate limit is exceeded (HTTP 429)."""


class ServiceUnavailableError(GnaniAPIError):
    """Raised when a downstream service is temporarily unavailable (HTTP 503)."""


class GnaniConnectionError(GnaniAPIError):
    """Raised when the API could not be reached or gave no response (timeout, dropped connection).

    There is no HTTP status.  ``request_not_sent`` is True when the request
    certainly never reached the server (so retrying is always safe); otherwise the
    server may already have received it.
    """

    def __init__(self, message: str, *, request_not_sent: bool = False) -> None:
        super().__init__(message)
        self.request_not_sent = request_not_sent
