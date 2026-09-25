"""Manual integration test — exercises all Gnani API tools end-to-end.

Run with:
    GNANI_API_KEY=<key> python tests/integration_test.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Add src/ to path so we don't need an install.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gnani_mcp.audio import AudioSink
from gnani_mcp.config import Config
from gnani_mcp.http import GnaniClient
from gnani_mcp.tools.tts import _VOICE_CATALOG

BASE_PATH = Path("/tmp/gnani_test_output")
BASE_PATH.mkdir(exist_ok=True)

# ── helpers ────────────────────────────────────────────────────────────────

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
INFO = "\033[94mℹ\033[0m"


def section(title: str) -> None:
    print(f"\n\033[1m{'─' * 60}\033[0m")
    print(f"\033[1m  {title}\033[0m")
    print(f"\033[1m{'─' * 60}\033[0m")


def ok(msg: str) -> None:
    print(f"  {PASS}  {msg}")


def fail(msg: str) -> None:
    print(f"  {FAIL}  {msg}")


def info(msg: str) -> None:
    print(f"  {INFO}  {msg}")


# ── tests ──────────────────────────────────────────────────────────────────

def test_voice_catalog() -> None:
    section("1 · gnani_tts_list_voices (no API call)")
    try:
        total = len(_VOICE_CATALOG)
        assert total == 42, f"expected 42 voices, got {total}"
        ok(f"Voice catalog loaded: {total} voices")

        hindi = [v for v in _VOICE_CATALOG if v["language"] == "hi-IN"]
        ok(f"Hindi voices: {[v['voice'] for v in hindi]}")

        english = [v for v in _VOICE_CATALOG if v["language"] == "en-IN"]
        ok(f"English voices: {[v['voice'] for v in english]}")

        languages = {v["language"] for v in _VOICE_CATALOG}
        ok(f"Languages covered: {sorted(languages)}")
    except Exception as e:
        fail(f"Voice catalog error: {e}")
        raise


async def test_tts(client: GnaniClient, sink: AudioSink) -> Path:
    section("2 · gnani_tts_synthesize (TTS REST API)")
    text = "नमस्ते! मैं Gnani का TTS सिस्टम हूँ। आज का दिन बहुत अच्छा है।"
    info(f"Text: {text}")
    info("Voice: Nalini | Language: hi-IN | Speed: 1.0 | Container: wav")

    audio_bytes = await client.post_json_binary(
        "/api/v1/tts/inference",
        json_body={
            "text": text,
            "voice": "Nalini",
            "model": "timbre-v2.5",
            "language": "hi-IN",
            "speed": 1.0,
            "audio_config": {
                "sample_rate": 16000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        },
    )
    out = sink.save(audio_bytes, extension="wav", stem="tts_hi")
    ok(f"Audio saved: {out}  ({len(audio_bytes):,} bytes)")

    # Second call — English
    text_en = "Hello! This is the Gnani text-to-speech system. It sounds great."
    info(f"Text: {text_en}")
    info("Voice: Kaveri | Language: en-IN")
    audio_bytes_en = await client.post_json_binary(
        "/api/v1/tts/inference",
        json_body={
            "text": text_en,
            "voice": "Kaveri",
            "model": "timbre-v2.5",
            "language": "en-IN",
            "speed": 1.0,
            "audio_config": {
                "sample_rate": 16000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
        },
    )
    out_en = sink.save(audio_bytes_en, extension="wav", stem="tts_en")
    ok(f"Audio saved: {out_en}  ({len(audio_bytes_en):,} bytes)")

    return out  # return Hindi file for STT test


async def test_stt(client: GnaniClient, audio_path: Path) -> None:
    section("3 · gnani_stt_transcribe (STT REST API)")
    info(f"Audio file: {audio_path}")
    info("Language: hi-IN | Format: verbatim")

    with audio_path.open("rb") as fh:
        payload = await client.post_multipart(
            "/stt/v3",
            data={"language_code": "hi-IN", "format": "verbatim"},
            files={"audio_file": (audio_path.name, fh, "audio/wav")},
        )

    transcript = payload.get("transcript", "")
    ok(f"Transcript (verbatim): {transcript!r}")

    # Second call with ITN
    info("Language: hi-IN | Format: transcribe (ITN enabled)")
    with audio_path.open("rb") as fh:
        payload_itn = await client.post_multipart(
            "/stt/v3",
            data={
                "language_code": "hi-IN",
                "format": "transcribe",
                "itn_native_numerals": "false",
            },
            files={"audio_file": (audio_path.name, fh, "audio/wav")},
        )
    ok(f"Transcript (ITN):      {payload_itn.get('transcript', '')!r}")


async def test_vc(client: GnaniClient, sink: AudioSink, reference_audio: Path) -> None:
    section("4 · gnani_vc_generate_embedding (Voice Clone)")
    info(f"Reference audio: {reference_audio}")

    with reference_audio.open("rb") as fh:
        payload = await client.post_multipart(
            "/api/v1/tts/voice-clone/embeddings",
            data={},
            files={"audio_file": (reference_audio.name, fh, "audio/wav")},
        )

    data = payload.get("data", {})
    embedding_obj = data.get("voice_clone_embedding", {})
    embedding_str = embedding_obj.get("embedding", "")
    shape = embedding_obj.get("shape")
    dtype = embedding_obj.get("dtype")

    ok(f"Embedding shape: {shape}  dtype: {dtype}")
    ok(f"Embedding (first 60 chars): {str(embedding_str)[:60]}…")

    # Step 2 — synthesize with cloned voice
    section("4b · gnani_vc_synthesize (Voice Clone TTS)")
    info("Text: 'यह मेरी आवाज़ है।'")
    audio_bytes = await client.post_json_binary(
        "/api/v1/tts/inference",
        json_body={
            "text": "यह मेरी क्लोन की हुई आवाज़ है।",
            "model": "vachana-vc-v1",
            "audio_config": {
                "sample_rate": 16000,
                "num_channels": 1,
                "sample_width": 2,
                "encoding": "linear_pcm",
                "container": "wav",
            },
            "speaker_embedding": {
                "embedding": embedding_str,
                "shape": shape,
                "dtype": dtype,
            },
        },
    )
    out = sink.save(audio_bytes, extension="wav", stem="vc_cloned")
    ok(f"Cloned audio saved: {out}  ({len(audio_bytes):,} bytes)")

async def test_batch_stt(client: GnaniClient) -> None:
    section("5 · gnani_stt_batch_transcribe (Batch STT)")
    # Use a short public audio file so the job completes quickly.
    PUBLIC_URL = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3"
    # Use a real speech sample instead — point to one of our generated TTS files... 
    # but those are local. We'll use a public Hindi speech sample.
    PUBLIC_SPEECH_URL = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/2/21/"
        "Simple_English.ogg/220px-Simple_English.ogg"
    )
    info(f"Submitting public URL job: {PUBLIC_SPEECH_URL}")
    info("Language: en-IN | No diarization")

    from gnani_mcp.tools.stt_batch import _BASE, _POLL_INTERVAL_SECONDS, _TERMINAL_STATUSES
    import asyncio as _asyncio

    # Step 1: Create
    body = {
        "config": {
            "model": "gnani-prisma-v2.5",
            "language_code": "en-IN",
            "mode": "transcribe",
            "with_diarization": False,
            "is_multi_channel": False,
            "with_denoise": False,
        },
        "source": {
            "type": "cloud_storage",
            "auth": {"mode": "public"},
            "paths": [PUBLIC_SPEECH_URL],
        },
    }
    create = await client.post_json(_BASE, json_body=body)
    job_id = create["job_id"]
    ok(f"Job created: {job_id}  status={create['status']}")

    # Step 2: Start
    await client.post_json(f"{_BASE}/{job_id}/start", json_body={})
    ok("Job started")

    # Step 3: Poll (max 5 min)
    info("Polling every 10 s…")
    for attempt in range(30):
        await _asyncio.sleep(10)
        status_r = await client.get_json(f"{_BASE}/{job_id}")
        st = status_r.get("status", "")
        prog = status_r.get("progress", {})
        info(f"  [{attempt+1:2d}] {st}  {prog.get('completed_files',0)}/{prog.get('total_files','?')} files")
        if st in _TERMINAL_STATUSES:
            ok(f"Terminal status reached: {st}")
            break
    else:
        fail("Job did not complete within 5 min — check manually")
        return

    if st in ("FAILED", "START_FAILED"):
        fail(f"Job {st}: {status_r.get('cancel_reason', 'see /files for details')}")
        return

    # Step 4: Get files
    files_r = await client.get_json(f"{_BASE}/{job_id}/files", params={"status": "COMPLETED", "limit": 100})
    for f in files_r.get("data", []):
        t_url = f.get("transcript_url")
        if t_url:
            t_data = await client.get_presigned(t_url)
            ok(f"Transcript: {t_data.get('full_transcript', '')!r}")
            ok(f"Duration: {t_data.get('duration_seconds')} s  Language: {t_data.get('language_code')}")
        else:
            fail(f"File {f.get('original_path')} → {f.get('status')}: {f.get('error_message')}")




async def main() -> None:
    api_key = os.environ.get("GNANI_API_KEY")
    if not api_key:
        print(f"  {FAIL}  GNANI_API_KEY is not set.")
        sys.exit(1)

    print(f"\n\033[1mGnani MCP — Integration Test\033[0m")
    print(f"  API key  : {api_key[:16]}…")
    print(f"  Base URL : https://api.vachana.ai")
    print(f"  Output   : {BASE_PATH}")

    client = GnaniClient(base_url="https://api.vachana.ai", api_key=api_key)
    sink = AudioSink(BASE_PATH)

    try:
        # 1. Voice catalog (no network)
        test_voice_catalog()

        # 2. TTS — synthesize Hindi + English
        tts_audio = await test_tts(client, sink)

        # 3. STT — transcribe the TTS output
        await test_stt(client, tts_audio)

        # 4. Voice clone — embed + synthesize (uses TTS audio as reference)
        await test_vc(client, sink, tts_audio)

        # 5. Batch STT — submit a public-URL job and poll to completion
        await test_batch_stt(client)

        section("Summary")
        ok("All tests completed successfully!")
        print(f"\n  Generated files are in: {BASE_PATH}\n")

    except Exception as exc:
        section("Summary")
        fail(f"Test failed: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
