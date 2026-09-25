"""Tests for gnani_mcp.http — GnaniClient error mapping."""

from __future__ import annotations

import httpx
import pytest
import respx

from gnani_mcp.exceptions import (
    AuthenticationError,
    GnaniAPIError,
    InvalidRequestError,
    RateLimitError,
    ServiceUnavailableError,
)
from gnani_mcp.http import GnaniClient

BASE_URL = "https://api.vachana.ai"


@pytest.fixture
def client() -> GnaniClient:
    return GnaniClient(base_url=BASE_URL, api_key="sk_test")


class TestAuthHeader:
    def test_missing_key_raises(self) -> None:
        c = GnaniClient(base_url=BASE_URL, api_key=None)
        with pytest.raises(AuthenticationError):
            c._auth_headers()

    def test_key_present(self) -> None:
        c = GnaniClient(base_url=BASE_URL, api_key="sk_abc")
        headers = c._auth_headers()
        assert headers["X-API-Key-ID"] == "sk_abc"


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("status_code", "error_type", "expected_exc"),
        [
            (400, "INVALID_REQUEST_ERROR", InvalidRequestError),
            (403, "FORBIDDEN", AuthenticationError),
            (429, "RATE_LIMIT_ERROR", RateLimitError),
            (503, "SERVICE_UNAVAILABLE", ServiceUnavailableError),
            (500, "API_ERROR", GnaniAPIError),
        ],
    )
    def test_raise_for_status(
        self,
        client: GnaniClient,
        status_code: int,
        error_type: str,
        expected_exc: type[GnaniAPIError],
    ) -> None:
        with pytest.raises(expected_exc):
            client._raise_from_response(
                _make_error_response(status_code, error_type, "test error")
            )


def _make_error_response(status_code: int, error_type: str, message: str) -> httpx.Response:
    import json

    body = json.dumps({"success": False, "error": {"type": error_type, "message": message}})
    return httpx.Response(status_code, text=body, headers={"content-type": "application/json"})
