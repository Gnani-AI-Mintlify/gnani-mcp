"""Text-to-Speech tools — wrap the Gnani Timbre v2.5 / v3.0 REST endpoint.

Endpoint: POST https://api.vachana.ai/api/v1/tts/inference
"""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from pydantic import Field

from gnani_mcp.tools._common import (
    AudioContainer,
    AudioEncoding,
    MP3Bitrate,
    TtsLanguageCode,
    classify_output,
    ready_ctx,
    resolve_sample_rate,
)
from gnani_mcp.voices import (
    AUDIO_TAGS,
    DEFAULT_TTS_MODEL,
    V3_LANGUAGES,
    TtsModel,
    describe_voices_v3,
    describe_voices_v25,
    get_catalog,
    inspect_audio_tags,
    resolve_voice,
)
from gnani_mcp.voices import (
    VOICE_CATALOG_V25 as _VOICE_CATALOG,  # noqa: F401 — kept for backwards-compatible imports
)

_TTS_PATH = "/api/v1/tts/inference"

# Default audio output configuration.
_DEFAULT_SAMPLE_RATE = 48_000
_DEFAULT_CONTAINER: AudioContainer = "wav"
_DEFAULT_ENCODING: AudioEncoding = "linear_pcm"

_AUDIO_TAGS_DOC = ", ".join(f"<{t}>" for t in AUDIO_TAGS)

# Accepted ``speed`` range per model. Timbre v3.0 accepts 0.8-1.2 (the service snaps it to
# 0.8, 1.0 or 1.2); Timbre v2.5 accepts any value from 0.85 to 1.15.
SPEED_RANGES: dict[str, tuple[float, float]] = {
    "timbre-v2.5": (0.85, 1.15),
    "timbre-v3.0": (0.8, 1.2),
}


def validate_speed(model: str, speed: float | None) -> float | None:
    """Check *speed* against the range for *model*. ``None`` (not set) is always valid."""
    if speed is None:
        return None
    low, high = SPEED_RANGES[model]
    if not low <= speed <= high:
        raise ValueError(
            f"speed {speed} is outside the range for {model}: {low} to {high}. "
            "Leave speed unset to use the voice's default."
        )
    return speed


def build_tts_warnings(model: str, text: str) -> list[str]:
    """Return non-fatal warnings about audio tags in *text* for *model*."""
    known, unknown = inspect_audio_tags(text)
    warnings: list[str] = []
    if model != "timbre-v3.0" and known:
        warnings.append(
            f"Audio tags {', '.join(f'<{t}>' for t in known)} are a Timbre v3.0 feature; "
            "with timbre-v2.5 they are removed from the text and not spoken. "
            "Set model='timbre-v3.0' to use them."
        )
    if model == "timbre-v3.0" and unknown:
        warnings.append(
            f"Unrecognised tag(s) {', '.join(f'<{t}>' for t in unknown)} will be stripped "
            f"silently. Supported tags: {_AUDIO_TAGS_DOC}."
        )
    return warnings


def register(mcp: FastMCP) -> None:
    """Register all TTS tools onto *mcp*."""

    @mcp.tool(
        name="gnani_tts_synthesize",
        description=(
            "Synthesize speech from text using the Gnani Timbre Text-to-Speech API. "
            "Returns an audio file saved to disk.\n\n"
            "**Models** (voices are NOT interchangeable between them):\n"
            "- ``timbre-v2.5`` (default) — 42 voices; each has one preferred language "
            "(10 Indian languages + Hinglish).\n"
            "- ``timbre-v3.0`` — 34 voices that each speak all 10 languages and support "
            f"inline audio tags: {_AUDIO_TAGS_DOC}. Tags apply from their position to the "
            "end of the text (or the next tag); ``<pauses>`` inserts silence and is never "
            "spoken. Tags count as billable characters.\n\n"
            "**Timbre v2.5 voices by language (all 42):**\n"
            f"{describe_voices_v25()}\n\n"
            "**Timbre v3.0 voices (all 34; every voice speaks all 10 languages):**\n"
            f"{describe_voices_v3()}\n\n"
            "Use ``gnani_tts_list_voices`` (with ``model``) to browse the full catalog with "
            "personas and descriptions.\n\n"
            "Numbers, currency, dates and IDs are normalised to spoken form automatically "
            "by the API — write text naturally."
        ),
    )
    async def gnani_tts_synthesize(
        ctx: Context,
        text: str = Field(
            description=(
                "Text to synthesize. With model='timbre-v3.0' it may contain inline audio "
                f"tags, e.g. 'Let me check. <pauses> Found it <laugh>'. Tags: {_AUDIO_TAGS_DOC}."
            ),
        ),
        voice: str = Field(
            description=(
                "Voice name from the catalog of the selected model (case-insensitive). "
                "timbre-v2.5 examples: 'Nalini' (Hindi F), 'Kaveri' (English F), 'Deepak' "
                "(Hindi M), 'Poorvi' (Hinglish F). timbre-v3.0 examples: 'Shivani' (F), "
                "'Avinash' (M)."
            ),
        ),
        model: TtsModel = Field(
            default=DEFAULT_TTS_MODEL,
            description=(
                "'timbre-v2.5' (default) or 'timbre-v3.0'. The model determines which "
                "voices are valid and whether audio tags are honoured."
            ),
        ),
        language: TtsLanguageCode = Field(
            default="auto",
            description=(
                "Language of the input text. Use 'auto' to detect from script. "
                "Supported: auto, hi-IN, en-IN, hi-en, ta-IN, te-IN, kn-IN, ml-IN, "
                "mr-IN, pa-IN, bn-IN, gu-IN. For timbre-v2.5 match the voice's preferred "
                "language; timbre-v3.0 voices speak all 10 languages."
            ),
        ),
        speed: float | None = Field(
            default=None,
            description=(
                "Playback speed multiplier. Optional: when omitted, the service uses the "
                "voice's recommended speed. Range depends on the model: timbre-v3.0 0.8 to 1.2 "
                "(snapped to 0.8, 1.0 or 1.2), timbre-v2.5 0.85 to 1.15. 1.0 = normal speed."
            ),
        ),
        sample_rate: int = Field(
            default=_DEFAULT_SAMPLE_RATE,
            description="Sample rate in Hz. Supported: 8000, 16000, 22050, 24000, 44100, 48000.",
        ),
        container: AudioContainer = Field(
            default=_DEFAULT_CONTAINER,
            description=(
                "Output audio container. Options: wav, mp3, ogg, raw, mulaw, alaw. "
                "Use 'mulaw' or 'alaw' for telephony (always 8000 Hz, regardless of sample_rate). "
                "Use 'ogg' for OGG Opus."
            ),
        ),
        encoding: AudioEncoding = Field(
            default=_DEFAULT_ENCODING,
            description=(
                "Audio encoding. Options: linear_pcm, pcm_s16le, pcm_mulaw, pcm_alaw, oggopus. "
                "Not required when container=mp3. pcm_mulaw / pcm_alaw are G.711 telephony "
                "encodings: the output is 8000 Hz whatever the container or sample_rate."
            ),
        ),
        bitrate: MP3Bitrate | None = Field(
            default=None,
            description="MP3 bitrate. Only used when container='mp3'. Options: 32k, 64k, 96k, 128k, 192k.",
        ),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)

        canonical_voice = resolve_voice(model, voice)
        speed = validate_speed(model, speed)
        warnings = build_tts_warnings(model, text)

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
            "voice": canonical_voice,
            "model": model,
            "language": language,
            "audio_config": audio_config,
        }
        if speed is not None:
            json_body["speed"] = speed

        audio_bytes = await sc.client.post_json_binary(_TTS_PATH, json_body=json_body)

        actual_rate, rate_warning = resolve_sample_rate(audio_bytes, sample_rate, container, encoding)
        if rate_warning:
            warnings.append(rate_warning)

        fmt = classify_output(audio_bytes, container, encoding)
        if fmt.warning:
            warnings.append(fmt.warning)

        out_path = sc.audio_sink.save(audio_bytes, extension=fmt.extension, stem="tts")

        result: dict[str, Any] = {
            "audio_file": str(out_path),
            "size_bytes": len(audio_bytes),
            "model": model,
            "voice": canonical_voice,
            "language": language,
            "container": fmt.container,
            "encoding": fmt.encoding,
            "sample_rate": actual_rate,
        }
        if warnings:
            result["warnings"] = warnings
        return result

    @mcp.tool(
        name="gnani_tts_list_voices",
        description=(
            "List available voices for a Gnani Timbre TTS model, with gender, persona "
            "and description. Use this to find the right voice before calling "
            "``gnani_tts_synthesize``.\n\n"
            "``model='timbre-v2.5'`` (default) returns 42 voices, each with one preferred "
            "language — filter with ``language`` (e.g. 'hi-IN'). "
            "``model='timbre-v3.0'`` returns 34 voices that all speak every supported "
            "language, so ``language`` is not a useful filter there.\n\n"
            "Optionally filter by ``gender`` ('Male' or 'Female')."
        ),
    )
    async def gnani_tts_list_voices(
        ctx: Context,
        model: TtsModel = Field(
            default=DEFAULT_TTS_MODEL,
            description="'timbre-v2.5' (default, 42 voices) or 'timbre-v3.0' (34 voices).",
        ),
        language: str | None = Field(
            default=None,
            description=(
                "Optional language code to filter by (e.g. 'hi-IN', 'en-IN', 'ta-IN'). "
                "timbre-v2.5 only: filters on each voice's preferred language. "
                "Returns all voices when omitted."
            ),
        ),
        gender: str | None = Field(
            default=None,
            description="Optional gender filter: 'Male' or 'Female'.",
        ),
    ) -> dict[str, Any]:
        catalog = get_catalog(model)

        if language is not None and model == "timbre-v2.5":
            catalog = [v for v in catalog if v["language"] == language]
        if gender is not None:
            catalog = [v for v in catalog if v["gender"].lower() == gender.lower()]

        result: dict[str, Any] = {
            "model": model,
            "total_voices": len(catalog),
            "voices": catalog,
        }
        if model == "timbre-v3.0":
            result["languages"] = V3_LANGUAGES
            result["audio_tags"] = list(AUDIO_TAGS)
        return result
