"""End-to-end tests: call the registered MCP tools in-memory against a mocked API."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from fastmcp import Client

from gnani_mcp.server import build_server

BASE = "https://api.vachana.ai"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setenv("GNANI_API_BASE_URL", BASE)
    monkeypatch.setenv("GNANI_MCP_BASE_PATH", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))


@pytest.fixture
def wav(tmp_path: Path) -> str:
    p = tmp_path / "clip.wav"
    p.write_bytes(b"RIFF....WAVEfmt ")
    return str(p)


async def _call(name: str, args: dict, *, raise_on_error: bool = True):
    async with Client(build_server()) as client:
        return await client.call_tool(name, args, raise_on_error=raise_on_error)


@pytest.mark.asyncio
async def test_tools_registered() -> None:
    async with Client(build_server()) as client:
        names = {t.name for t in await client.list_tools()}
    assert {
        "gnani_stt_transcribe",
        "gnani_stt_batch_transcribe",
        "gnani_stt_batch_list_jobs",
        "gnani_tts_synthesize",
        "gnani_tts_list_voices",
    } <= names


@pytest.mark.asyncio
@respx.mock
async def test_stt_v3_request_and_response(wav: str) -> None:
    route = respx.post(f"{BASE}/stt/v3").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "request_id": "r1",
                "transcript": "नमस्ते",
                "model": "prisma-v3.0",
                "detected_language_code": "hi-IN",
            },
        )
    )
    res = await _call(
        "gnani_stt_transcribe",
        {
            "audio_path": wav,
            "model": "prisma-v3.0",
            "language_code": "hi-IN,en-IN",
            "format": "codemix",
            "keyterms": ["HDFC Bank"],
        },
    )
    body = route.calls.last.request.content
    assert b'name="model"\r\n\r\nprisma-v3.0' in body
    assert b"hi-IN,en-IN" in body
    assert b'name="keyterms"\r\n\r\n["HDFC Bank"]' in body
    data = res.data
    assert data["detected_language_code"] == "hi-IN"
    assert data["model"] == "prisma-v3.0"


@pytest.mark.asyncio
@respx.mock
async def test_stt_default_stays_v25(wav: str) -> None:
    route = respx.post(f"{BASE}/stt/v3").mock(
        return_value=httpx.Response(200, json={"success": True, "transcript": "hi", "timestamp": "t"})
    )
    res = await _call("gnani_stt_transcribe", {"audio_path": wav, "language_code": "hi-IN"})
    body = route.calls.last.request.content
    assert b'name="model"' not in body
    assert b'name="format"\r\n\r\nverbatim' in body
    assert res.data["timestamp"] == "t"
    assert "detected_language_code" not in res.data


@pytest.mark.asyncio
async def test_stt_v3_only_options_rejected_on_v25(wav: str) -> None:
    res = await _call(
        "gnani_stt_transcribe",
        {"audio_path": wav, "language_code": "hi-IN", "keyterms": ["x"]},
        raise_on_error=False,
    )
    assert res.is_error


@pytest.mark.asyncio
@respx.mock
async def test_tts_v3_with_tags(tmp_path: Path) -> None:
    route = respx.post(f"{BASE}/api/v1/tts/inference").mock(
        return_value=httpx.Response(200, content=b"RIFFaudio", headers={"content-type": "audio/wav"})
    )
    res = await _call(
        "gnani_tts_synthesize",
        {"text": "Hello <pauses> there", "voice": "shivani", "model": "timbre-v3.0", "language": "en-IN"},
    )
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "timbre-v3.0"
    assert sent["voice"] == "Shivani"
    assert sent["text"] == "Hello <pauses> there"
    assert "warnings" not in res.data
    assert Path(res.data["audio_file"]).read_bytes() == b"RIFFaudio"


@pytest.mark.asyncio
@respx.mock
async def test_tts_v25_tags_warn() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=b"x"))
    res = await _call("gnani_tts_synthesize", {"text": "Hi <laugh>", "voice": "Nalini"})
    assert res.data["model"] == "timbre-v2.5"
    assert "timbre-v3.0" in res.data["warnings"][0]


@pytest.mark.asyncio
async def test_tts_wrong_voice_for_model() -> None:
    res = await _call(
        "gnani_tts_synthesize", {"text": "Hi", "voice": "Shivani"}, raise_on_error=False
    )
    assert res.is_error


@pytest.mark.asyncio
async def test_list_voices_v3() -> None:
    res = await _call("gnani_tts_list_voices", {"model": "timbre-v3.0", "gender": "Male"})
    assert res.data["total_voices"] == 6
    assert "laugh" in res.data["audio_tags"]


@pytest.mark.asyncio
@respx.mock
async def test_batch_list_jobs() -> None:
    route = respx.get(f"{BASE}/stt/v3/batch/jobs").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [{"job_id": "j1", "status": "COMPLETED"}],
                "pagination": {"has_more": False, "next_cursor": None},
            },
        )
    )
    res = await _call("gnani_stt_batch_list_jobs", {"status": "completed", "limit": 5})
    q = route.calls.last.request.url.params
    assert q["status"] == "COMPLETED"
    assert q["limit"] == "5"
    assert res.data["jobs"][0]["job_id"] == "j1"
