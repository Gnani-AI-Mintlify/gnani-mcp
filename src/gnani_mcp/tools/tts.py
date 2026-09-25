"""Text-to-Speech tools — wrap the Gnani Timbre v2.5 REST endpoint.

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
    TtsVoice,
    ready_ctx,
)

_TTS_PATH = "/api/v1/tts/inference"

# Default audio output configuration.
_DEFAULT_SAMPLE_RATE = 48_000
_DEFAULT_CONTAINER: AudioContainer = "wav"
_DEFAULT_ENCODING: AudioEncoding = "linear_pcm"

# Voice catalog — matches Available Voices page (42 voices, Timbre v2.5).
_VOICE_CATALOG: list[dict[str, str]] = [
    {"voice": "Ambuja",  "gender": "Female", "language": "hi-IN", "persona": "Professional",          "description": "Clear, composed virtual assistant"},
    {"voice": "Asmita",  "gender": "Female", "language": "ta-IN", "persona": "Professional",          "description": "Polished, refined, smooth corporate voice"},
    {"voice": "Bhavna",  "gender": "Female", "language": "hi-IN", "persona": "Friendly",              "description": "Friendly voice for customer support"},
    {"voice": "Brinda",  "gender": "Female", "language": "ta-IN", "persona": "Professional",          "description": "Steady, even-paced professional voice"},
    {"voice": "Chitra",  "gender": "Female", "language": "hi-IN", "persona": "Warm, empathetic",      "description": "Mature voice for customer care"},
    {"voice": "Deepak",  "gender": "Male",   "language": "hi-IN", "persona": "Professional",          "description": "Clear, measured voice for corporate use"},
    {"voice": "Devika",  "gender": "Female", "language": "en-IN", "persona": "Professional",          "description": "Authoritative voice for customer support"},
    {"voice": "Dhruva",  "gender": "Male",   "language": "bn-IN", "persona": "Conversational",        "description": "Casual, relatable voice for conversations"},
    {"voice": "Falak",   "gender": "Female", "language": "gu-IN", "persona": "Conversational",        "description": "Youthful, clear voice for narration"},
    {"voice": "Girish",  "gender": "Male",   "language": "en-IN", "persona": "Expressive, energetic", "description": "Warm voice with natural storytelling"},
    {"voice": "Hemraj",  "gender": "Male",   "language": "hi-IN", "persona": "Confident, authoritative", "description": "Confident voice for demos"},
    {"voice": "Ishaan",  "gender": "Male",   "language": "mr-IN", "persona": "Professional",          "description": "Clear voice for instructions and narration"},
    {"voice": "Jalaj",   "gender": "Male",   "language": "hi-IN", "persona": "Expressive, energetic", "description": "Expressive voice for storytelling"},
    {"voice": "Jwala",   "gender": "Female", "language": "hi-IN", "persona": "Friendly",              "description": "Friendly, approachable everyday voice"},
    {"voice": "Kaveri",  "gender": "Female", "language": "en-IN", "persona": "Professional",          "description": "Firm voice for customer support"},
    {"voice": "Kavin",   "gender": "Male",   "language": "kn-IN", "persona": "Professional",          "description": "Firm, articulate voice for presentations"},
    {"voice": "Kirra",   "gender": "Female", "language": "bn-IN", "persona": "Conversational",        "description": "Soft-spoken voice for casual conversations"},
    {"voice": "Lavanya", "gender": "Female", "language": "te-IN", "persona": "Warm, empathetic",      "description": "Soft, empathetic voice for care and support"},
    {"voice": "Lehara",  "gender": "Female", "language": "te-IN", "persona": "Warm, empathetic",      "description": "Gentle, reassuring voice for comfort and trust"},
    {"voice": "Mehuli",  "gender": "Female", "language": "pa-IN", "persona": "Expressive, energetic", "description": "Expressive voice for commercials and promotions"},
    {"voice": "Nalini",  "gender": "Female", "language": "hi-IN", "persona": "Friendly",              "description": "Friendly voice for playful conversations"},
    {"voice": "Noopur",  "gender": "Female", "language": "ta-IN", "persona": "Friendly",              "description": "Warm voice for everyday conversations"},
    {"voice": "Omkar",   "gender": "Male",   "language": "hi-IN", "persona": "Confident, authoritative", "description": "Energetic voice for customer support"},
    {"voice": "Poorvi",  "gender": "Female", "language": "hi-en", "persona": "Conversational",        "description": "Natural voice for bilingual conversations"},
    {"voice": "Pranav",  "gender": "Male",   "language": "en-IN", "persona": "Friendly",              "description": "Friendly voice for customer support"},
    {"voice": "Reshma",  "gender": "Female", "language": "ml-IN", "persona": "Friendly",              "description": "Bright voice for greetings and support"},
    {"voice": "Riyaan",  "gender": "Male",   "language": "ml-IN", "persona": "Conversational",        "description": "Easygoing voice for casual conversations"},
    {"voice": "Roopesh", "gender": "Male",   "language": "hi-IN", "persona": "Professional",          "description": "Grounded, knowledgeable, professional voice"},
    {"voice": "Saanvi",  "gender": "Female", "language": "kn-IN", "persona": "Expressive, energetic", "description": "Lively voice for ads and promotions"},
    {"voice": "Shlok",   "gender": "Male",   "language": "en-IN", "persona": "Conversational",        "description": "Warm, conversational voice"},
    {"voice": "Suhana",  "gender": "Female", "language": "te-IN", "persona": "Warm, empathetic",      "description": "Calm, soothing voice with confidence"},
    {"voice": "Trisha",  "gender": "Female", "language": "ta-IN", "persona": "Friendly",              "description": "Warm, approachable voice for guidance"},
    {"voice": "Trupti",  "gender": "Female", "language": "en-IN", "persona": "Professional",          "description": "Upbeat, articulate voice with maturity"},
    {"voice": "Urmila",  "gender": "Female", "language": "hi-IN", "persona": "Professional",          "description": "Refined voice for formal announcements"},
    {"voice": "Varuni",  "gender": "Female", "language": "te-IN", "persona": "Conversational",        "description": "Clear, natural voice for everyday use"},
    {"voice": "Vedika",  "gender": "Female", "language": "ta-IN", "persona": "Professional",          "description": "Crisp, articulate voice for information"},
    {"voice": "Veera",   "gender": "Male",   "language": "gu-IN", "persona": "Friendly",              "description": "Friendly voice for casual conversations"},
    {"voice": "Vikrant", "gender": "Male",   "language": "hi-IN", "persona": "Conversational",        "description": "Warm, genuine conversational voice"},
    {"voice": "Yashvi",  "gender": "Female", "language": "hi-IN", "persona": "Warm, empathetic",      "description": "Gentle, reassuring voice for comfort"},
    {"voice": "Yukti",   "gender": "Female", "language": "te-IN", "persona": "Friendly",              "description": "Warm, welcoming voice that puts listeners at ease"},
    {"voice": "Zahira",  "gender": "Female", "language": "mr-IN", "persona": "Expressive, energetic", "description": "Energetic voice for sales and casual chat"},
    {"voice": "Zayan",   "gender": "Male",   "language": "pa-IN", "persona": "Warm, empathetic",      "description": "Soft, caring voice for empathetic conversations"},
]


def register(mcp: FastMCP) -> None:
    """Register all TTS tools onto *mcp*."""

    @mcp.tool(
        name="gnani_tts_synthesize",
        description=(
            "Synthesize speech from text using the Gnani Timbre v2.5 Text-to-Speech API. "
            "Returns an audio file saved to disk. Supports 10 Indian languages + Hinglish, "
            "with 42 voices.\n\n"
            "**Recommended voices by language:**\n"
            "- Hindi (hi-IN): Nalini (F), Deepak (M), Bhavna (F), Roopesh (M)\n"
            "- English (en-IN): Kaveri (F), Trupti (F), Pranav (M), Shlok (M)\n"
            "- Hinglish (hi-en): Poorvi (F)\n"
            "- Tamil (ta-IN): Asmita (F), Trisha (F), Vedika (F)\n"
            "- Telugu (te-IN): Suhana (F), Lavanya (F), Varuni (F)\n"
            "- Kannada (kn-IN): Saanvi (F), Kavin (M)\n"
            "- Malayalam (ml-IN): Reshma (F), Riyaan (M)\n"
            "- Marathi (mr-IN): Zahira (F), Ishaan (M)\n"
            "- Bengali (bn-IN): Kirra (F), Dhruva (M)\n"
            "- Gujarati (gu-IN): Falak (F), Veera (M)\n"
            "- Punjabi (pa-IN): Mehuli (F), Zayan (M)\n\n"
            "Use ``gnani_tts_list_voices`` to browse the full catalog with descriptions.\n\n"
            "**Important:** Pass numbers, dates, and currency as spoken words to avoid "
            "mispronunciations. See the Input Formatting Guide at docs.gnani.ai."
        ),
    )
    async def gnani_tts_synthesize(
        ctx: Context,
        text: str = Field(
            description=(
                "Text to synthesize. Pass numbers/dates/currency as spoken words for best results "
                "(e.g. 'five thousand rupees' rather than '₹5000')."
            ),
        ),
        voice: TtsVoice = Field(
            description=(
                "Voice name from the Timbre v2.5 catalog. "
                "Examples: 'Nalini' (Hindi F), 'Kaveri' (English F), 'Deepak' (Hindi M), "
                "'Poorvi' (Hinglish F)."
            ),
        ),
        language: TtsLanguageCode = Field(
            default="auto",
            description=(
                "Language of the input text. Use 'auto' to detect from script. "
                "Supported: auto, hi-IN, en-IN, hi-en, ta-IN, te-IN, kn-IN, ml-IN, "
                "mr-IN, pa-IN, bn-IN, gu-IN."
            ),
        ),
        speed: float = Field(
            default=1.0,
            description=(
                "Playback speed multiplier. Range 0.85 (slowest) to 1.15 (fastest). "
                "1.0 = normal speed."
            ),
            ge=0.85,
            le=1.15,
        ),
        sample_rate: int = Field(
            default=_DEFAULT_SAMPLE_RATE,
            description="Sample rate in Hz. Supported: 8000, 16000, 22050, 24000, 44100, 48000.",
        ),
        container: AudioContainer = Field(
            default=_DEFAULT_CONTAINER,
            description=(
                "Output audio container. Options: wav, mp3, ogg, raw, mulaw, alaw. "
                "Use 'mulaw' or 'alaw' for telephony (forces 8000 Hz). "
                "Use 'ogg' for OGG Opus."
            ),
        ),
        encoding: AudioEncoding = Field(
            default=_DEFAULT_ENCODING,
            description=(
                "Audio encoding. Options: linear_pcm, pcm_s16le, pcm_mulaw, pcm_alaw, oggopus. "
                "Not required when container=mp3."
            ),
        ),
        bitrate: MP3Bitrate | None = Field(
            default=None,
            description="MP3 bitrate. Only used when container='mp3'. Options: 32k, 64k, 96k, 128k, 192k.",
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
            "voice": voice,
            "model": "timbre-v2.5",
            "language": language,
            "speed": speed,
            "audio_config": audio_config,
        }

        audio_bytes = await sc.client.post_json_binary(_TTS_PATH, json_body=json_body)

        out_path = sc.audio_sink.save(
            audio_bytes,
            extension=container if container not in ("mulaw", "alaw", "raw") else "raw",
            stem="tts",
        )

        return {
            "audio_file": str(out_path),
            "size_bytes": len(audio_bytes),
            "voice": voice,
            "language": language,
            "container": container,
            "sample_rate": sample_rate,
        }

    @mcp.tool(
        name="gnani_tts_list_voices",
        description=(
            "List all available voices for the Gnani Timbre v2.5 TTS model. "
            "Returns the full catalog of 42 voices with language, gender, persona, "
            "and description. Use this to find the right voice before calling "
            "``gnani_tts_synthesize``.\n\n"
            "Filter by language to narrow results "
            "(e.g. language='hi-IN' returns all Hindi voices)."
        ),
    )
    async def gnani_tts_list_voices(
        ctx: Context,
        language: str | None = Field(
            default=None,
            description=(
                "Optional language code to filter by "
                "(e.g. 'hi-IN', 'en-IN', 'ta-IN'). "
                "Returns all voices when omitted."
            ),
        ),
        gender: str | None = Field(
            default=None,
            description="Optional gender filter: 'Male' or 'Female'.",
        ),
    ) -> dict[str, Any]:
        catalog = _VOICE_CATALOG

        if language is not None:
            catalog = [v for v in catalog if v["language"] == language]
        if gender is not None:
            catalog = [v for v in catalog if v["gender"].lower() == gender.lower()]

        return {
            "model": "timbre-v2.5",
            "total_voices": len(catalog),
            "voices": catalog,
        }
