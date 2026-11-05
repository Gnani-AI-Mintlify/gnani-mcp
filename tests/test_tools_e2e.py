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


@pytest.mark.asyncio
@respx.mock
async def test_batch_cancels_orphan_job_when_start_fails(wav: str) -> None:
    respx.post(f"{BASE}/stt/v3/batch/jobs").mock(return_value=httpx.Response(201, json={"job_id": "j9", "status": "CREATED"}))
    respx.post(f"{BASE}/stt/v3/batch/jobs/j9/start").mock(
        return_value=httpx.Response(400, json={"error": {"type": "INVALID_REQUEST_ERROR", "message": "nope"}})
    )
    cancel = respx.post(f"{BASE}/stt/v3/batch/jobs/j9/cancel").mock(return_value=httpx.Response(200, json={"status": "CANCELLED"}))
    res = await _call("gnani_stt_batch_transcribe", {"audio_path": wav, "language_code": "hi-IN"}, raise_on_error=False)
    assert res.is_error
    assert cancel.called


# ── Batch: failed files are reported with the API's error message ───────────

_JOBS = f"{BASE}/stt/v3/batch/jobs"


def _file(name: str, status: str, *, url: str | None = None, error: str | None = None, fid: str | None = None) -> dict:
    return {
        "file_id": fid or name,
        "original_path": name,
        "status": status,
        "duration_seconds": "3.00",
        "transcript_url": url,
        "error_message": error,
    }


@pytest.mark.asyncio
@respx.mock
async def test_batch_get_transcripts_reports_failed_files() -> None:
    respx.get(f"{_JOBS}/jp").mock(
        return_value=httpx.Response(200, json={"job_id": "jp", "status": "PARTIAL_FAILURE", "progress": {"total_files": 2}})
    )
    files = respx.get(f"{_JOBS}/jp/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    _file("good.wav", "COMPLETED", url="https://s3.example/t.json"),
                    _file("silence.wav", "FAILED", error="no speech detected in 3s of audio"),
                ],
                "pagination": {"has_more": False, "next_cursor": None},
            },
        )
    )
    respx.get("https://s3.example/t.json").mock(
        return_value=httpx.Response(200, json={"language_code": "hi-IN", "duration_seconds": 3, "full_transcript": "नमस्ते"})
    )
    res = await _call("gnani_stt_batch_get_transcripts", {"job_id": "jp"})

    # No status filter: failed files must be requested too.
    assert "status" not in files.calls.last.request.url.params
    ok, bad = res.data["transcripts"]
    assert ok["status"] == "COMPLETED" and ok["full_transcript"] == "नमस्ते"
    assert bad == {
        "file": "silence.wav",
        "file_id": "silence.wav",
        "status": "FAILED",
        "duration_seconds": "3.00",
        "error": "no speech detected in 3s of audio",
    }
    assert "silence.wav: no speech detected" in res.data["warning"]


@pytest.mark.asyncio
@respx.mock
async def test_batch_get_transcripts_on_failed_job_returns_errors() -> None:
    respx.get(f"{_JOBS}/jf").mock(return_value=httpx.Response(200, json={"job_id": "jf", "status": "FAILED"}))
    respx.get(f"{_JOBS}/jf/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [_file("empty.wav", "FAILED", error="object uploads/x/empty.wav is empty")],
                "pagination": {"has_more": False, "next_cursor": None},
            },
        )
    )
    res = await _call("gnani_stt_batch_get_transcripts", {"job_id": "jf"})
    assert res.data["transcripts"][0]["error"] == "object uploads/x/empty.wav is empty"


@pytest.mark.asyncio
@respx.mock
async def test_batch_get_transcripts_pages_through_all_files() -> None:
    respx.get(f"{_JOBS}/jm").mock(return_value=httpx.Response(200, json={"job_id": "jm", "status": "FAILED"}))

    def page(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("cursor") == "c2":
            return httpx.Response(
                200,
                json={"data": [_file("b.wav", "FAILED", error="e2")], "pagination": {"has_more": False, "next_cursor": None}},
            )
        return httpx.Response(
            200,
            json={"data": [_file("a.wav", "FAILED", error="e1")], "pagination": {"has_more": True, "next_cursor": "c2"}},
        )

    route = respx.get(f"{_JOBS}/jm/files").mock(side_effect=page)
    res = await _call("gnani_stt_batch_get_transcripts", {"job_id": "jm"})
    assert [t["file"] for t in res.data["transcripts"]] == ["a.wav", "b.wav"]
    assert route.call_count == 2


@pytest.mark.asyncio
@respx.mock
async def test_batch_get_transcripts_stops_on_repeating_cursor() -> None:
    respx.get(f"{_JOBS}/jr").mock(return_value=httpx.Response(200, json={"job_id": "jr", "status": "FAILED"}))
    route = respx.get(f"{_JOBS}/jr/files").mock(
        return_value=httpx.Response(
            200,
            json={"data": [_file("a.wav", "FAILED", error="e")], "pagination": {"has_more": True, "next_cursor": "same"}},
        )
    )
    await _call("gnani_stt_batch_get_transcripts", {"job_id": "jr"})
    assert route.call_count == 2  # second page repeats the cursor -> stop


@pytest.mark.asyncio
@respx.mock
async def test_batch_transcribe_failed_job_surfaces_file_error(
    wav: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gnani_mcp.tools.stt_batch._POLL_INTERVAL_SECONDS", 0)
    respx.post(_JOBS).mock(return_value=httpx.Response(201, json={"job_id": "jt", "status": "CREATED"}))
    respx.post(f"{_JOBS}/jt/start").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{_JOBS}/jt").mock(
        return_value=httpx.Response(200, json={"job_id": "jt", "status": "FAILED", "progress": {"failed_files": 1}})
    )
    respx.get(f"{_JOBS}/jt/files").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [_file("clip.wav", "FAILED", error="no speech detected in 3s of audio")],
                "pagination": {"has_more": False, "next_cursor": None},
            },
        )
    )
    res = await _call("gnani_stt_batch_transcribe", {"audio_path": wav, "language_code": "hi-IN"})
    assert res.data["status"] == "FAILED"
    assert "clip.wav: no speech detected in 3s of audio" in res.data["error"]
    assert res.data["transcripts"][0]["status"] == "FAILED"


@pytest.mark.asyncio
@respx.mock
async def test_batch_transcribe_failed_job_falls_back_when_listing_fails(
    wav: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("gnani_mcp.tools.stt_batch._POLL_INTERVAL_SECONDS", 0)
    respx.post(_JOBS).mock(return_value=httpx.Response(201, json={"job_id": "jt", "status": "CREATED"}))
    respx.post(f"{_JOBS}/jt/start").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{_JOBS}/jt").mock(return_value=httpx.Response(200, json={"job_id": "jt", "status": "FAILED"}))
    respx.get(f"{_JOBS}/jt/files").mock(return_value=httpx.Response(500, text="boom"))
    res = await _call("gnani_stt_batch_transcribe", {"audio_path": wav, "language_code": "hi-IN"})
    assert res.data["status"] == "FAILED"
    assert "no per-file error details" in res.data["error"]


# ── G.711 output is always 8 kHz: report the real sample rate ───────────────

from gnani_mcp.tools._common import effective_sample_rate  # noqa: E402


@pytest.mark.parametrize(
    ("requested", "container", "encoding", "expected", "warns"),
    [
        (48000, "wav", "linear_pcm", 48000, False),
        (16000, "raw", "pcm_s16le", 16000, False),
        (24000, "mp3", "linear_pcm", 24000, False),
        (16000, "ogg", "oggopus", 16000, False),
        (48000, "mulaw", "linear_pcm", 8000, True),
        (16000, "alaw", "linear_pcm", 8000, True),
        (48000, "wav", "pcm_mulaw", 8000, True),  # encoding alone is enough
        (44100, "raw", "pcm_alaw", 8000, True),
        (8000, "mulaw", "pcm_mulaw", 8000, False),  # already 8 kHz: nothing to warn about
    ],
)
def test_effective_sample_rate(requested: int, container: str, encoding: str, expected: int, warns: bool) -> None:
    rate, warning = effective_sample_rate(requested, container, encoding)
    assert rate == expected
    assert (warning is not None) is warns


@pytest.mark.asyncio
@respx.mock
async def test_tts_mulaw_reports_real_sample_rate() -> None:
    route = respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=b"\xff" * 64))
    res = await _call("gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri", "container": "mulaw", "sample_rate": 48000})
    # The request is forwarded unchanged; only the reported rate is corrected.
    assert json.loads(route.calls.last.request.content)["audio_config"]["sample_rate"] == 48000
    assert res.data["sample_rate"] == 8000
    assert "8000 Hz" in res.data["warnings"][0]


@pytest.mark.asyncio
@respx.mock
async def test_tts_wav_keeps_requested_sample_rate() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=b"RIFFaudio"))
    res = await _call("gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri", "sample_rate": 24000})
    assert res.data["sample_rate"] == 24000
    assert "warnings" not in res.data


@pytest.mark.asyncio
@respx.mock
async def test_vc_alaw_reports_real_sample_rate() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=b"\xd5" * 64))
    res = await _call(
        "gnani_vc_synthesize",
        {
            "text": "Hi",
            "speaker_embedding": {"embedding": "AAAA", "shape": [1, 4], "dtype": "torch.bfloat16"},
            "container": "alaw",
        },
    )
    assert res.data["sample_rate"] == 8000
    assert "ignored" in res.data["warnings"][0]


# ── Saved file follows the real content, not the requested container ────────

from gnani_mcp.audio import detect_audio_container  # noqa: E402
from gnani_mcp.tools._common import classify_output  # noqa: E402

_WAV = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVEfmt " + b"\x00" * 40
_OGG = b"OggS" + b"\x00" * 40 + b"OpusHead"
_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413  # MPEG-1 L3, 128 kbps, 44.1 kHz -> 417 bytes
_MULAW = b"\xff\xff\x7e\x7e" * 64


def test_detect_audio_container() -> None:
    assert detect_audio_container(_WAV) == "wav"
    assert detect_audio_container(_OGG) == "ogg"
    assert detect_audio_container(b"ID3\x04\x00" + b"\x00" * 20) == "mp3"
    assert detect_audio_container(_MP3_FRAME * 3) == "mp3"
    assert detect_audio_container(_MULAW) is None
    assert detect_audio_container(b"") is None


def test_detect_does_not_mistake_raw_pcm_for_mp3() -> None:
    # First 4 bytes happen to look like an MP3 frame header, but no second frame follows.
    assert detect_audio_container(b"\xff\xfb\x90\x00" + b"\x01\x02" * 600) is None


_WAV_ALAW = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVEfmt " + b"\x10\x00\x00\x00" + b"\x06\x00" + b"\x00" * 24


@pytest.mark.parametrize(
    ("data", "container", "encoding", "ext", "real", "real_enc", "warns"),
    [
        (_WAV, "wav", "linear_pcm", "wav", "wav", "linear_pcm", False),
        (_WAV_ALAW, "wav", "pcm_alaw", "wav", "wav", "pcm_alaw", False),  # WAV header says A-law
        (_OGG, "ogg", "oggopus", "ogg", "ogg", "oggopus", False),
        (_MP3_FRAME * 2, "mp3", "linear_pcm", "mp3", "mp3", "mp3", False),
        (b"\x01\x00" * 100, "raw", "pcm_s16le", "raw", "raw", "pcm_s16le", False),
        (_MULAW, "raw", "pcm_mulaw", "raw", "raw", "pcm_mulaw", False),  # raw container holding G.711
        (_MULAW, "mulaw", "pcm_mulaw", "raw", "mulaw", "pcm_mulaw", False),
        (_MULAW, "alaw", "linear_pcm", "raw", "alaw", "pcm_alaw", False),  # container decides
        # container and encoding disagree -> the bytes win:
        (_MULAW, "wav", "pcm_mulaw", "raw", "mulaw", "pcm_mulaw", True),
        (_MULAW, "mp3", "pcm_alaw", "raw", "alaw", "pcm_alaw", True),
        (_OGG, "wav", "oggopus", "ogg", "ogg", "oggopus", True),
        # unrecognisable bytes + non-G.711 encoding: trust the request, no rename
        (b"RIFFaudio", "wav", "linear_pcm", "wav", "wav", "linear_pcm", False),
    ],
)
def test_classify_output(
    data: bytes, container: str, encoding: str, ext: str, real: str, real_enc: str, warns: bool
) -> None:
    out = classify_output(data, container, encoding)
    assert (out.extension, out.container, out.encoding) == (ext, real, real_enc)
    assert (out.warning is not None) is warns


@pytest.mark.asyncio
@respx.mock
async def test_tts_wav_with_mulaw_encoding_is_saved_as_raw_mulaw() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_MULAW))
    res = await _call(
        "gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri", "container": "wav", "encoding": "pcm_mulaw"}
    )
    assert res.data["audio_file"].endswith(".raw")
    assert Path(res.data["audio_file"]).read_bytes() == _MULAW
    assert res.data["container"] == "mulaw"
    assert res.data["encoding"] == "pcm_mulaw"
    assert res.data["sample_rate"] == 8000
    assert any("headerless mu-law" in w for w in res.data["warnings"])


@pytest.mark.asyncio
@respx.mock
async def test_tts_wav_with_oggopus_is_saved_as_ogg() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_OGG))
    res = await _call(
        "gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri", "container": "wav", "encoding": "oggopus"}
    )
    assert res.data["audio_file"].endswith(".ogg")
    assert res.data["container"] == "ogg"
    assert res.data["encoding"] == "oggopus"
    assert "OGG/Opus" in res.data["warnings"][0]


@pytest.mark.asyncio
@respx.mock
async def test_vc_wav_with_mulaw_encoding_is_saved_as_raw() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_MULAW))
    res = await _call(
        "gnani_vc_synthesize",
        {
            "text": "Hi",
            "speaker_embedding": {"embedding": "AAAA", "shape": [1, 4], "dtype": "torch.bfloat16"},
            "encoding": "pcm_mulaw",
        },
    )
    assert res.data["audio_file"].endswith(".raw")
    assert res.data["container"] == "mulaw"
    assert res.data["encoding"] == "pcm_mulaw"


@pytest.mark.asyncio
@respx.mock
async def test_tts_plain_wav_reports_linear_pcm_encoding() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_WAV))
    res = await _call("gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri"})
    assert (res.data["container"], res.data["encoding"]) == ("wav", "linear_pcm")


# ── gnani_stt_transcribe: filename is required for base64 / URL audio ───────

import base64  # noqa: E402

_STT_OK = {"success": True, "transcript": "hi", "model": "prisma-v2.5", "request_id": "r"}


def _err_text(res) -> str:
    return "".join(getattr(c, "text", "") for c in res.content)


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("filename", [None, "", "   ", "recording", ".wav"])
async def test_stt_base64_without_usable_filename_fails_early(filename: str | None) -> None:
    route = respx.post(f"{BASE}/stt/v3").mock(return_value=httpx.Response(200, json=_STT_OK))
    args = {"audio_base64": base64.b64encode(b"RIFF....WAVEfmt ").decode(), "language_code": "hi-IN"}
    if filename is not None:
        args["filename"] = filename
    res = await _call("gnani_stt_transcribe", args, raise_on_error=False)
    assert res.is_error
    assert "filename" in _err_text(res) and "audio_base64" in _err_text(res)
    assert not route.called  # never reaches the API


@pytest.mark.asyncio
@respx.mock
async def test_stt_url_without_filename_fails_early_and_does_not_download() -> None:
    api = respx.post(f"{BASE}/stt/v3").mock(return_value=httpx.Response(200, json=_STT_OK))
    dl = respx.get("https://files.example/hi.wav").mock(return_value=httpx.Response(200, content=b"x"))
    res = await _call(
        "gnani_stt_transcribe", {"audio_url": "https://files.example/hi.wav", "language_code": "hi-IN"}, raise_on_error=False
    )
    assert res.is_error and "audio_url" in _err_text(res) and "e.g. 'call.wav'" in _err_text(res)
    assert not dl.called and not api.called  # the extension in the URL is deliberately not used


@pytest.mark.asyncio
@respx.mock
async def test_stt_base64_with_filename_still_works() -> None:
    route = respx.post(f"{BASE}/stt/v3").mock(return_value=httpx.Response(200, json=_STT_OK))
    res = await _call(
        "gnani_stt_transcribe",
        {"audio_base64": base64.b64encode(b"RIFF....WAVEfmt ").decode(), "filename": "call.WAV", "language_code": "hi-IN"},
    )
    assert res.data["transcript"] == "hi"
    assert b'filename="' in route.calls.last.request.content and b".WAV" in route.calls.last.request.content


@pytest.mark.asyncio
async def test_stt_local_path_needs_no_filename(wav: str) -> None:
    with respx.mock:
        respx.post(f"{BASE}/stt/v3").mock(return_value=httpx.Response(200, json=_STT_OK))
        res = await _call("gnani_stt_transcribe", {"audio_path": wav, "language_code": "hi-IN"})
    assert res.data["transcript"] == "hi"


# ── audio_url download failures: clear messages, no leaked signed query ─────


@pytest.mark.asyncio
@respx.mock
async def test_stt_url_404_gives_clear_message_without_query_string() -> None:
    respx.get("https://files.example/missing.wav").mock(return_value=httpx.Response(404))
    res = await _call(
        "gnani_stt_transcribe",
        {"audio_url": "https://files.example/missing.wav?X-Amz-Signature=SECRET", "filename": "a.wav", "language_code": "hi-IN"},
        raise_on_error=False,
    )
    text = _err_text(res)
    assert "HTTP 404" in text and "https://files.example/missing.wav" in text
    assert "SECRET" not in text


@pytest.mark.asyncio
@respx.mock
async def test_stt_url_returning_html_is_rejected() -> None:
    respx.get("https://files.example/page").mock(
        return_value=httpx.Response(200, content=b"<html></html>", headers={"content-type": "text/html; charset=utf-8"})
    )
    res = await _call(
        "gnani_stt_transcribe",
        {"audio_url": "https://files.example/page", "filename": "a.wav", "language_code": "hi-IN"},
        raise_on_error=False,
    )
    assert res.is_error and "text/html" in _err_text(res) and "not audio" in _err_text(res)


@pytest.mark.asyncio
@respx.mock
async def test_stt_url_network_error_names_the_error_type() -> None:
    respx.get("https://files.example/slow.wav").mock(side_effect=httpx.ReadTimeout(""))
    res = await _call(
        "gnani_stt_transcribe",
        {"audio_url": "https://files.example/slow.wav", "filename": "a.wav", "language_code": "hi-IN"},
        raise_on_error=False,
    )
    assert "ReadTimeout" in _err_text(res) and "Could not download" in _err_text(res)


@pytest.mark.asyncio
@respx.mock
async def test_stt_url_octet_stream_is_accepted() -> None:
    respx.get("https://files.example/a.wav").mock(
        return_value=httpx.Response(200, content=b"RIFF....WAVEfmt ", headers={"content-type": "application/octet-stream"})
    )
    respx.post(f"{BASE}/stt/v3").mock(return_value=httpx.Response(200, json=_STT_OK))
    res = await _call(
        "gnani_stt_transcribe", {"audio_url": "https://files.example/a.wav", "filename": "a.wav", "language_code": "hi-IN"}
    )
    assert res.data["transcript"] == "hi"


@pytest.mark.asyncio
@respx.mock
async def test_vc_embedding_still_works_without_filename() -> None:
    # Voice clone does not need an extension, so the STT filename rule must not leak into it.
    respx.post(f"{BASE}/api/v1/tts/voice-clone/embeddings").mock(
        return_value=httpx.Response(
            200, json={"success": True, "data": {"voice_clone_embedding": {"embedding": "A", "shape": [1], "dtype": "x"}}}
        )
    )
    res = await _call("gnani_vc_generate_embedding", {"audio_base64": base64.b64encode(b"RIFF....WAVEfmt ").decode()})
    assert res.data["speaker_embedding"]["embedding"] == "A"


# ── The file's own header decides the reported sample rate ──────────────────

import struct  # noqa: E402

from gnani_mcp.audio import detect_sample_rate  # noqa: E402


def _wav_with_rate(rate: int) -> bytes:
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    data = b"\x00\x00" * 8
    return (
        b"RIFF" + struct.pack("<I", 4 + 8 + len(fmt) + 8 + len(data)) + b"WAVE"
        + b"fmt " + struct.pack("<I", len(fmt)) + fmt + b"data" + struct.pack("<I", len(data)) + data
    )


def _mp3_22k() -> bytes:  # MPEG-2 layer III, 32 kbps, 22.05 kHz -> 104-byte frames
    return (b"\xff\xf3\x40\xc4" + b"\x00" * 100) * 3


def _mp3_48k() -> bytes:  # MPEG-1 layer III, 128 kbps, 48 kHz -> 384-byte frames
    return (b"\xff\xfb\x94\xc4" + b"\x00" * 380) * 3


def _ogg_opus(rate: int) -> bytes:
    return b"OggS" + b"\x00" * 23 + b"OpusHead" + bytes([1, 1]) + b"\x00\x00" + struct.pack("<I", rate) + b"\x00" * 8


def test_detect_sample_rate() -> None:
    assert detect_sample_rate(_wav_with_rate(24000)) == 24000
    assert detect_sample_rate(_mp3_22k()) == 22050
    assert detect_sample_rate(_mp3_48k()) == 48000
    assert detect_sample_rate(b"ID3\x04\x00\x00\x00\x00\x00\x0a" + b"\x00" * 10 + _mp3_22k()) == 22050  # skips the ID3 tag
    assert detect_sample_rate(_ogg_opus(16000)) == 16000
    assert detect_sample_rate(_MULAW) is None  # headerless: no rate to read
    assert detect_sample_rate(_WAV) is None  # header with rate 0 is ignored
    assert detect_sample_rate(b"") is None


@pytest.mark.asyncio
@respx.mock
async def test_tts_mp3_32k_reports_the_rate_the_api_really_returned() -> None:
    # Live behaviour: mp3 at 32k, requested 48 kHz, comes back at 22.05 kHz.
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_mp3_22k()))
    res = await _call(
        "gnani_tts_synthesize",
        {"text": "Hi", "voice": "Kaveri", "container": "mp3", "bitrate": "32k", "sample_rate": 48000},
    )
    assert res.data["sample_rate"] == 22050
    assert "48000 was requested" in res.data["warnings"][0] and "22050 Hz" in res.data["warnings"][0]
    assert res.data["container"] == "mp3"


@pytest.mark.asyncio
@respx.mock
async def test_tts_mp3_with_honoured_rate_has_no_warning() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_mp3_48k()))
    res = await _call("gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri", "container": "mp3", "sample_rate": 48000})
    assert res.data["sample_rate"] == 48000
    assert "warnings" not in res.data


@pytest.mark.asyncio
@respx.mock
async def test_tts_wav_reports_its_header_rate() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_wav_with_rate(16000)))
    res = await _call("gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri", "sample_rate": 16000})
    assert res.data["sample_rate"] == 16000 and "warnings" not in res.data


@pytest.mark.asyncio
@respx.mock
async def test_tts_ogg_rate_rounded_by_opus_is_reported() -> None:
    # Live behaviour: Opus has no 22.05 kHz, so the header says 24 kHz.
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_ogg_opus(24000)))
    res = await _call(
        "gnani_tts_synthesize",
        {"text": "Hi", "voice": "Kaveri", "container": "ogg", "encoding": "oggopus", "sample_rate": 22050},
    )
    assert res.data["sample_rate"] == 24000
    assert "22050 was requested" in res.data["warnings"][0]


@pytest.mark.asyncio
@respx.mock
async def test_headerless_g711_still_uses_the_8khz_rule() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_MULAW))
    res = await _call("gnani_tts_synthesize", {"text": "Hi", "voice": "Kaveri", "container": "mulaw", "sample_rate": 48000})
    assert res.data["sample_rate"] == 8000 and "always 8000 Hz" in res.data["warnings"][0]


@pytest.mark.asyncio
@respx.mock
async def test_vc_mp3_reports_real_rate() -> None:
    respx.post(f"{BASE}/api/v1/tts/inference").mock(return_value=httpx.Response(200, content=_mp3_22k()))
    res = await _call(
        "gnani_vc_synthesize",
        {
            "text": "Hi",
            "speaker_embedding": {"embedding": "AAAA", "shape": [1, 4], "dtype": "torch.bfloat16"},
            "container": "mp3",
            "sample_rate": 44100,
        },
    )
    assert res.data["sample_rate"] == 22050 and "44100 was requested" in res.data["warnings"][0]


# ── Batch: reject unusable inputs before a job exists; explain START_FAILED ─


def _mock_batch_lifecycle(job_id: str, status_body: dict):
    create = respx.post(_JOBS).mock(return_value=httpx.Response(201, json={"job_id": job_id, "status": "CREATED"}))
    respx.post(f"{_JOBS}/{job_id}/start").mock(return_value=httpx.Response(200, json={}))
    respx.get(f"{_JOBS}/{job_id}").mock(return_value=httpx.Response(200, json={"job_id": job_id, **status_body}))
    return create


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize(
    "bad_url",
    ["", "   ", "banana", "banana?sig=SECRET", "ftp://host/a.wav", "file:///etc/passwd", "https://", "//host/a.wav", "http://:80/a.wav"],
)
async def test_batch_rejects_unusable_audio_url_without_creating_a_job(bad_url: str) -> None:
    create = respx.post(_JOBS).mock(return_value=httpx.Response(201, json={"job_id": "j", "status": "CREATED"}))
    res = await _call("gnani_stt_batch_transcribe", {"audio_url": bad_url, "language_code": "hi-IN"}, raise_on_error=False)
    assert res.is_error
    assert "audio_url" in _err_text(res)
    assert "SECRET" not in _err_text(res)
    assert not create.called  # nothing is created, so no dead job is left behind


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("url", ["https://files.example/call.wav", "http://files.example/call.wav", "  https://files.example/call.wav?sig=1  "])
async def test_batch_accepts_http_and_https_urls_and_strips_whitespace(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gnani_mcp.tools.stt_batch._POLL_INTERVAL_SECONDS", 0)
    create = _mock_batch_lifecycle("jb", {"status": "COMPLETED", "progress": {"total_files": 1}})
    respx.get(f"{_JOBS}/jb/files").mock(
        return_value=httpx.Response(200, json={"data": [], "pagination": {"has_more": False, "next_cursor": None}})
    )
    await _call("gnani_stt_batch_transcribe", {"audio_url": url, "language_code": "hi-IN"})
    assert json.loads(create.calls.last.request.content)["source"]["paths"] == [url.strip()]


@pytest.mark.asyncio
@respx.mock
async def test_batch_rejects_empty_local_file_without_creating_a_job(tmp_path: Path) -> None:
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    create = respx.post(_JOBS).mock(return_value=httpx.Response(201, json={"job_id": "j", "status": "CREATED"}))
    res = await _call("gnani_stt_batch_transcribe", {"audio_path": str(empty), "language_code": "hi-IN"}, raise_on_error=False)
    assert res.is_error and "empty.wav" in _err_text(res) and "0 bytes" in _err_text(res)
    assert not create.called


@pytest.mark.asyncio
@respx.mock
async def test_batch_start_failed_keeps_server_reason_and_adds_input_and_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("gnani_mcp.tools.stt_batch._POLL_INTERVAL_SECONDS", 0)
    _mock_batch_lifecycle(
        "js", {"status": "START_FAILED", "cancel_reason": "All provided paths were invalid — nothing to process."}
    )
    res = await _call(
        "gnani_stt_batch_transcribe",
        {"audio_url": "https://files.example/gone.wav?X-Amz-Signature=SECRET", "language_code": "hi-IN"},
    )
    err = res.data["error"]
    assert res.data["status"] == "START_FAILED" and res.data["job_id"] == "js"
    assert err.startswith("All provided paths were invalid — nothing to process.")  # the server's own reason, first
    assert "https://files.example/gone.wav" in err and "SECRET" not in err
    assert "public link" in err


@pytest.mark.asyncio
@respx.mock
async def test_batch_start_failed_without_reason_has_a_default(monkeypatch: pytest.MonkeyPatch, wav: str) -> None:
    monkeypatch.setattr("gnani_mcp.tools.stt_batch._POLL_INTERVAL_SECONDS", 0)
    _mock_batch_lifecycle("jn", {"status": "START_FAILED", "cancel_reason": None})
    res = await _call("gnani_stt_batch_transcribe", {"audio_path": wav, "language_code": "hi-IN"})
    assert res.data["error"].startswith("The job failed to start.")
    assert "clip.wav" in res.data["error"] and "uploaded file" in res.data["error"]
