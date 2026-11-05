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

    def test_source_header_identifies_mcp(self) -> None:
        c = GnaniClient(base_url=BASE_URL, api_key="sk_abc")
        assert c._auth_headers()["X-Source"] == "mcp"

    @respx.mock
    async def test_source_header_sent_on_the_wire(self, client: GnaniClient) -> None:
        route = respx.post(f"{BASE_URL}/stt/v3").mock(
            return_value=httpx.Response(200, json={"success": True})
        )
        await client.post_multipart("/stt/v3", data={"language_code": "hi-IN"}, files={"audio_file": ("a.wav", b"x", "audio/wav")})
        assert route.calls.last.request.headers["x-source"] == "mcp"
        assert route.calls.last.request.headers["x-api-key-id"] == "sk_test"


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


# ── Error-message parsing: one test per envelope the live API really sends ──

from gnani_mcp.exceptions import GnaniConnectionError  # noqa: E402
from gnani_mcp.http import parse_error_response  # noqa: E402


def _resp(status: int, *, json_body=None, text: str | None = None) -> httpx.Response:
    if json_body is not None:
        return httpx.Response(status, json=json_body)
    return httpx.Response(status, text=text or "")


@pytest.mark.parametrize(
    ("resp", "message", "code", "etype"),
    [
        # shape A: STT / TTS envelope
        (_resp(400, json_body={"success": False, "error": {"type": "INVALID_REQUEST_ERROR", "message": "bad"}}),
         "bad", None, "INVALID_REQUEST_ERROR"),
        # shape C: TTS / voice clone ("success":false + message) — the real sample_rate rejection
        (_resp(400, json_body={"success": False, "status_code": 400,
                               "message": "Invalid request: Value error, sample_rate must be one of [8000, 16000], got 12345 at body -> audio_config -> sample_rate"}),
         "Invalid request: Value error, sample_rate must be one of [8000, 16000], got 12345 at body -> audio_config -> sample_rate", None, "API_ERROR"),
        # shape D: batch API, "error" is a string code
        (_resp(404, json_body={"error": "JOB_NOT_FOUND", "message": "Job 0000 not found"}),
         "Job 0000 not found", "JOB_NOT_FOUND", "API_ERROR"),
        (_resp(409, json_body={"error": "JOB_ALREADY_COMPLETED", "message": "Job has already finished with status 'COMPLETED'"}),
         "Job has already finished with status 'COMPLETED'", "JOB_ALREADY_COMPLETED", "API_ERROR"),
        # shape B: voice clone detail dict, code maps onto a typed error
        (_resp(429, json_body={"detail": {"error_code": "RATE_LIMITED", "message": "Rate limit exceeded", "status_code": 429}}),
         "Rate limit exceeded", "RATE_LIMITED", "RATE_LIMIT_ERROR"),
        # FastAPI validation error (HTTP 422): location is shown, the 'path'/'body' prefix is dropped
        (_resp(422, json_body={"detail": [{"type": "uuid_parsing", "loc": ["path", "job_id"],
                                           "msg": "Input should be a valid UUID, invalid character: found `n` at 0", "input": "nope"}]}),
         "job_id: Input should be a valid UUID, invalid character: found `n` at 0", None, "API_ERROR"),
        (_resp(422, json_body={"detail": [{"loc": ["body", "audio_config", "sample_rate"], "msg": "bad"},
                                          {"loc": ["body", "text"], "msg": "required"}]}),
         "audio_config.sample_rate: bad; text: required", None, "API_ERROR"),
        (_resp(400, json_body={"detail": "plain detail"}), "plain detail", None, "API_ERROR"),
        # plain text, empty body, non-object JSON: never lose the text
        (_resp(400, text="Unsupported audio format. Supported formats: wav, mp3"),
         "Unsupported audio format. Supported formats: wav, mp3", None, "API_ERROR"),
        (_resp(500, text="Internal server error occurred. Please try again later."),
         "Internal server error occurred. Please try again later.", None, "API_ERROR"),
        (_resp(404, text=""), "Not Found", None, "API_ERROR"),
        (_resp(500, json_body=["weird"]), '["weird"]', None, "API_ERROR"),
        # unknown JSON object: raw text rather than a guess
        (_resp(500, json_body={"foo": "bar"}), '{"foo":"bar"}', None, "API_ERROR"),
    ],
)
def test_parse_error_response(resp: httpx.Response, message: str, code: str | None, etype: str) -> None:
    assert parse_error_response(resp) == (message, code, etype)


def test_error_string_includes_api_code_but_not_the_json_wrapper(client: GnaniClient) -> None:
    resp = _resp(404, json_body={"error": "JOB_NOT_FOUND", "message": "Job 0000 not found"})
    with pytest.raises(GnaniAPIError) as info:
        client._raise_from_response(resp)
    assert str(info.value) == "[HTTP 404 JOB_NOT_FOUND] Job 0000 not found"
    assert info.value.code == "JOB_NOT_FOUND" and info.value.status_code == 404


def test_error_string_without_code(client: GnaniClient) -> None:
    resp = _resp(400, json_body={"success": False, "message": "Text is required", "status_code": 400})
    with pytest.raises(InvalidRequestError) as info:
        client._raise_from_response(resp)
    assert str(info.value) == "[HTTP 400] Text is required"


# ── Network failures: clear, and honest about whether a retry is safe ───────


class TestConnectionErrors:
    @pytest.mark.asyncio
    @respx.mock
    async def test_read_timeout_on_post_warns_it_may_have_been_processed(self, client: GnaniClient) -> None:
        respx.post(f"{BASE_URL}/stt/v3/batch/jobs").mock(side_effect=httpx.ReadTimeout(""))  # httpx's text is empty
        with pytest.raises(GnaniConnectionError) as info:
            await client.post_json("/stt/v3/batch/jobs", json_body={})
        text = str(info.value)
        assert "POST /stt/v3/batch/jobs" in text and "did not respond within 120s" in text
        assert "may already have received and processed" in text
        assert info.value.request_not_sent is False
        assert info.value.status_code is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_read_timeout_on_get_is_safe_to_retry(self, client: GnaniClient) -> None:
        respx.get(f"{BASE_URL}/x").mock(side_effect=httpx.ReadTimeout(""))
        with pytest.raises(GnaniConnectionError, match="read-only request, so it is safe to retry"):
            await client.get_json("/x")

    @pytest.mark.asyncio
    @respx.mock
    async def test_connect_error_means_request_not_sent(self, client: GnaniClient) -> None:
        respx.post(f"{BASE_URL}/x").mock(side_effect=httpx.ConnectError("All connection attempts failed"))
        with pytest.raises(GnaniConnectionError) as info:
            await client.post_json("/x", json_body={})
        assert info.value.request_not_sent is True
        assert "could not connect" in str(info.value) and "safe to retry" in str(info.value)
        assert "All connection attempts failed" in str(info.value)

    @pytest.mark.asyncio
    @respx.mock
    async def test_dropped_connection(self, client: GnaniClient) -> None:
        respx.post(f"{BASE_URL}/x").mock(side_effect=httpx.RemoteProtocolError("Server disconnected without sending a response."))
        with pytest.raises(GnaniConnectionError, match="closed the connection without a response"):
            await client.post_json("/x", json_body={})

    @pytest.mark.asyncio
    @respx.mock
    async def test_network_errors_are_not_retried(self, client: GnaniClient) -> None:
        route = respx.post(f"{BASE_URL}/x").mock(side_effect=httpx.ReadTimeout(""))
        with pytest.raises(GnaniConnectionError):
            await client.post_json("/x", json_body={})
        assert route.call_count == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_presigned_download_failure_does_not_leak_the_signed_url(self, client: GnaniClient) -> None:
        respx.get("https://s3.example/t.json").mock(side_effect=httpx.ReadTimeout(""))
        with pytest.raises(GnaniConnectionError) as info:
            await client.get_presigned("https://s3.example/t.json?X-Amz-Signature=SECRET")
        assert "transcript download" in str(info.value) and "SECRET" not in str(info.value)
