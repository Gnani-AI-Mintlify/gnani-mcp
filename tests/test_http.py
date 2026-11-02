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


async def _no_sleep(_delay: float) -> None:
    return None


@pytest.fixture
def client() -> GnaniClient:
    return GnaniClient(base_url=BASE_URL, api_key="sk_test", sleep=_no_sleep)


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


class TestRateLimitRetry:
    RATE_LIMITED = {"detail": {"error_code": "RATE_LIMITED", "message": "Rate limit exceeded", "status_code": 429}}

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_429_then_succeeds(self) -> None:
        delays: list[float] = []

        async def record(d: float) -> None:
            delays.append(d)

        c = GnaniClient(base_url=BASE_URL, api_key="sk_test", sleep=record)
        route = respx.get(f"{BASE_URL}/x").mock(
            side_effect=[
                httpx.Response(429, json=self.RATE_LIMITED),
                httpx.Response(429, json=self.RATE_LIMITED),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        assert await c.get_json("/x") == {"ok": True}
        assert route.call_count == 3
        assert len(delays) == 2
        assert delays[1] > delays[0]  # exponential backoff
        await c.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_honours_retry_after(self) -> None:
        delays: list[float] = []

        async def record(d: float) -> None:
            delays.append(d)

        c = GnaniClient(base_url=BASE_URL, api_key="sk_test", sleep=record)
        respx.post(f"{BASE_URL}/x").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "3"}, json=self.RATE_LIMITED),
                httpx.Response(200, json={"ok": True}),
            ]
        )
        await c.post_json("/x", json_body={})
        assert delays == [3.0]
        await c.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_gives_up_after_max_retries(self) -> None:
        c = GnaniClient(base_url=BASE_URL, api_key="sk_test", max_retries=2, sleep=_no_sleep)
        route = respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(429, json=self.RATE_LIMITED))
        with pytest.raises(RateLimitError):
            await c.get_json("/x")
        assert route.call_count == 3  # 1 try + 2 retries
        await c.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_multipart_file_is_resent_in_full(self, tmp_path) -> None:
        f = tmp_path / "a.wav"
        f.write_bytes(b"AUDIO-BYTES")
        c = GnaniClient(base_url=BASE_URL, api_key="sk_test", sleep=_no_sleep)
        route = respx.post(f"{BASE_URL}/up").mock(
            side_effect=[httpx.Response(429, json=self.RATE_LIMITED), httpx.Response(200, json={"ok": True})]
        )
        with f.open("rb") as fh:
            await c.post_multipart("/up", data={}, files={"audio_file": ("a.wav", fh, "audio/wav")})
        assert b"AUDIO-BYTES" in route.calls[0].request.content
        assert b"AUDIO-BYTES" in route.calls[1].request.content
        await c.aclose()

    @pytest.mark.asyncio
    @respx.mock
    async def test_non_429_errors_are_not_retried(self) -> None:
        c = GnaniClient(base_url=BASE_URL, api_key="sk_test", sleep=_no_sleep)
        route = respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(503, json={"error": {"type": "SERVICE_UNAVAILABLE", "message": "down"}}))
        with pytest.raises(ServiceUnavailableError):
            await c.get_json("/x")
        assert route.call_count == 1
        await c.aclose()
