"""Voice Clone tools — generate speaker embeddings and synthesize with a cloned voice.

Voice cloning is a two-step process:
  1. ``gnani_vc_generate_embedding``  — upload reference audio → get speaker_embedding
  2. ``gnani_vc_synthesize``          — pass embedding + text → get cloned audio

Endpoint (both steps share the same inference path):
  POST https://api.vachana.ai/api/v1/tts/voice-clone/embeddings  (step 1)
  POST https://api.vachana.ai/api/v1/tts/inference               (step 2)
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from pydantic import Field

from gnani_mcp.tools._common import (
    AudioContainer,
    AudioEncoding,
    MP3Bitrate,
    guess_audio_mime,
    ready_ctx,
    resolve_file_input,
)

_EMBEDDINGS_PATH = "/api/v1/tts/voice-clone/embeddings"
_VC_INFERENCE_PATH = "/api/v1/tts/inference"

_DEFAULT_SAMPLE_RATE = 44_100
_DEFAULT_CONTAINER: AudioContainer = "wav"
_DEFAULT_ENCODING: AudioEncoding = "linear_pcm"


def register(mcp: FastMCP) -> None:
    """Register all Voice Clone tools onto *mcp*."""

    @mcp.tool(
        name="gnani_vc_generate_embedding",
        description=(
            "Step 1 of voice cloning — extract a speaker embedding from a reference audio clip.\n\n"
            "Upload 5–30 seconds of clean, single-speaker audio to obtain a "
            "``speaker_embedding`` object. Cache this result — you only need to generate it "
            "once per voice.\n\n"
            "Pass the returned ``speaker_embedding`` to ``gnani_vc_synthesize`` to synthesize "
            "speech in the cloned voice.\n\n"
            "**Supported audio formats:** WAV, MP3, OGG, FLAC, AAC, M4A.\n"
            "**Best results:** use 10–30 s of clean speech, minimal background noise, "
            "single speaker only."
        ),
    )
    async def gnani_vc_generate_embedding(
        ctx: Context,
        audio_path: str | None = Field(
            default=None,
            description="Absolute local path to the reference audio file.",
        ),
        audio_base64: str | None = Field(
            default=None,
            description="Base64-encoded reference audio. Provide ``filename`` to preserve extension.",
        ),
        audio_url: str | None = Field(
            default=None,
            description="HTTP/HTTPS URL of the reference audio file.",
        ),
        filename: str | None = Field(
            default=None,
            description="Filename with extension (e.g. 'reference.wav'). Required for base64/URL.",
        ),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)

        async with resolve_file_input(
            file_path=audio_path,
            file_base64=audio_base64,
            file_url=audio_url,
            filename=filename,
        ) as path:
            with path.open("rb") as fh:
                files = {"audio_file": (path.name, fh, guess_audio_mime(path))}
                payload = await sc.client.post_multipart(
                    _EMBEDDINGS_PATH, data={}, files=files
                )

        # Unwrap the nested response envelope.
        data = payload.get("data", {})
        embedding_obj = data.get("voice_clone_embedding", {})

        return {
            "success": payload.get("success", True),
            "message": payload.get("message", "Voice embeddings generated successfully"),
            "speaker_embedding": {
                "embedding": embedding_obj.get("embedding"),
                "shape": embedding_obj.get("shape"),
                "dtype": embedding_obj.get("dtype"),
            },
        }

    @mcp.tool(
        name="gnani_vc_synthesize",
        description=(
            "Step 2 of voice cloning — synthesize speech in a cloned voice.\n\n"
            "Pass the ``speaker_embedding`` returned by ``gnani_vc_generate_embedding`` "
            "along with your text to synthesize audio in the cloned voice. "
            "The full audio is returned as a file saved to disk.\n\n"
            "**Tip:** store the embedding once and reuse it for all synthesis calls "
            "with that voice — there is no need to re-generate it."
        ),
    )
    async def gnani_vc_synthesize(
        ctx: Context,
        text: str = Field(
            description="Text to synthesize in the cloned voice.",
        ),
        speaker_embedding: dict[str, Any] = Field(
            description=(
                "Speaker embedding from ``gnani_vc_generate_embedding``. "
                "Must contain 'embedding' (string), 'shape' (list of ints), "
                "and 'dtype' (string, e.g. 'torch.bfloat16')."
            ),
        ),
        sample_rate: int = Field(
            default=_DEFAULT_SAMPLE_RATE,
            description="Sample rate in Hz. Supported: 8000, 16000, 22050, 24000, 44100.",
        ),
        container: AudioContainer = Field(
            default=_DEFAULT_CONTAINER,
            description="Output audio container: wav, mp3, ogg, raw, mulaw, alaw.",
        ),
        encoding: AudioEncoding = Field(
            default=_DEFAULT_ENCODING,
            description="Audio encoding: linear_pcm, pcm_s16le, pcm_mulaw, pcm_alaw, oggopus.",
        ),
        bitrate: MP3Bitrate | None = Field(
            default=None,
            description="MP3 bitrate (only when container='mp3'): 96k, 128k, or 192k.",
        ),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)

        audio_config: dict[str, Any] = {
            "sample_rate": sample_rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": encoding,
            "container": container,
        }
        if bitrate is not None:
            audio_config["bitrate"] = bitrate

        json_body: dict[str, Any] = {
            "text": text,
            "model": "vachana-vc-v1",
            "audio_config": audio_config,
            "speaker_embedding": speaker_embedding,
        }

        audio_bytes = await sc.client.post_json_binary(_VC_INFERENCE_PATH, json_body=json_body)

        out_path = sc.audio_sink.save(
            audio_bytes,
            extension=container if container not in ("mulaw", "alaw", "raw") else "raw",
            stem="vc",
        )

        return {
            "audio_file": str(out_path),
            "size_bytes": len(audio_bytes),
            "container": container,
            "sample_rate": sample_rate,
        }
