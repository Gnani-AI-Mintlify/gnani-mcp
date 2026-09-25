"""Speech-to-Text tool — wraps the Gnani Prisma v2.5 REST endpoint.

Endpoint: POST https://api.vachana.ai/stt/v3
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastmcp import Context, FastMCP
from pydantic import Field

from gnani_mcp.tools._common import (
    SttLanguageCode,
    guess_audio_mime,
    ready_ctx,
    resolve_file_input,
)

_STT_PATH = "/stt/v3"


def register(mcp: FastMCP) -> None:
    """Register all STT tools onto *mcp*."""

    @mcp.tool(
        name="gnani_stt_transcribe",
        description=(
            "Transcribe an audio file (≤ 60 s, ideally ≤ 30 s) using the Gnani Prisma v2.5 "
            "Speech-to-Text API. Supports 10 Indian languages.\n\n"
            "**Supported languages:** Bengali (bn-IN), English India (en-IN), Gujarati (gu-IN), "
            "Hindi (hi-IN), Kannada (kn-IN), Malayalam (ml-IN), Marathi (mr-IN), Punjabi (pa-IN), "
            "Tamil (ta-IN), Telugu (te-IN).\n\n"
            "**Supported formats:** WAV, MP3, OGG, FLAC, AAC, M4A.\n\n"
            "Set ``format='transcribe'`` to enable Inverse Text Normalization (ITN) — numbers, "
            "currency, dates, and phone numbers are written in conventional form (e.g. "
            "\"five thousand rupees\" → \"₹5,000\").\n\n"
            "Use ``enable_substitution=True`` with a ``substitution_map`` to apply "
            "find-and-replace rules on the final transcript (max 10 rules)."
        ),
    )
    async def gnani_stt_transcribe(
        ctx: Context,
        audio_path: str | None = Field(
            default=None,
            description="Absolute local path to the audio file (e.g. '/home/user/call.wav').",
        ),
        audio_base64: str | None = Field(
            default=None,
            description="Base64-encoded audio data. Provide ``filename`` to preserve extension.",
        ),
        audio_url: str | None = Field(
            default=None,
            description="HTTP/HTTPS URL of the audio file. Provide ``filename`` to preserve extension.",
        ),
        filename: str | None = Field(
            default=None,
            description=(
                "Filename including extension (e.g. 'recording.wav'). "
                "Required when using ``audio_base64`` or ``audio_url`` so the MIME type "
                "can be determined correctly."
            ),
        ),
        language_code: SttLanguageCode = Field(
            description=(
                "BCP-47 language code for the audio. "
                "Supported: bn-IN, en-IN, gu-IN, hi-IN, kn-IN, ml-IN, mr-IN, pa-IN, ta-IN, te-IN."
            ),
        ),
        format: str = Field(
            default="verbatim",
            description=(
                "'verbatim' (default) — raw spoken-form output. "
                "'transcribe' — enables Inverse Text Normalization (ITN): numbers, currency, "
                "dates, and phone numbers written in conventional form."
            ),
        ),
        itn_native_numerals: bool = Field(
            default=False,
            description=(
                "When format='transcribe', set True to render digits in the native script "
                "of the target language (e.g. ₹५,००० instead of ₹5,000 for Hindi). "
                "Has no effect when format='verbatim'."
            ),
        ),
        enable_substitution: bool = Field(
            default=False,
            description=(
                "Set True to apply find-and-replace rules from ``substitution_map`` "
                "to the final transcript after recognition and ITN."
            ),
        ),
        substitution_map: list[dict[str, Any]] | None = Field(
            default=None,
            description=(
                "List of substitution rules (max 10). Each rule: "
                "{\"patterns\": [\"ok\", \"okay\"], \"replacement\": \"acknowledged\"}. "
                "Only evaluated when enable_substitution=True."
            ),
        ),
        request_id: str | None = Field(
            default=None,
            description="Optional correlation ID for this request (useful for support / logging).",
        ),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)

        async with resolve_file_input(
            file_path=audio_path,
            file_base64=audio_base64,
            file_url=audio_url,
            filename=filename,
        ) as path:
            form_data = _build_form_data(
                language_code=language_code,
                fmt=format,
                itn_native_numerals=itn_native_numerals,
                enable_substitution=enable_substitution,
                substitution_map=substitution_map,
                request_id=request_id,
            )

            with path.open("rb") as fh:
                files = {"audio_file": (path.name, fh, guess_audio_mime(path))}
                payload = await sc.client.post_multipart(
                    _STT_PATH, data=form_data, files=files
                )

        return {
            "success": payload.get("success", True),
            "transcript": payload.get("transcript", ""),
            "request_id": payload.get("request_id"),
            "timestamp": payload.get("timestamp"),
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_form_data(
    *,
    language_code: str,
    fmt: str,
    itn_native_numerals: bool,
    enable_substitution: bool,
    substitution_map: list[dict[str, Any]] | None,
    request_id: str | None,
) -> dict[str, str]:
    """Build the ``multipart/form-data`` field dict for the STT endpoint."""
    data: dict[str, str] = {
        "language_code": language_code,
        "format": fmt,
        "itn_native_numerals": str(itn_native_numerals).lower(),
        "enable_substitution": str(enable_substitution).lower(),
    }
    if substitution_map is not None and enable_substitution:
        data["substitution_map"] = json.dumps(substitution_map)
    if request_id is not None:
        data["request_id"] = request_id
    return data
