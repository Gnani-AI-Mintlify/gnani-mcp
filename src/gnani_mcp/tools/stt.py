"""Speech-to-Text tool — wraps the Gnani Prisma (v2.5 / v3.0) REST endpoint.

Endpoint: POST https://api.vachana.ai/stt/v3

The ``3`` in ``/stt/v3`` is the URL version, not the model version — the
``model`` form field selects Prisma v2.5 (default) or Prisma v3.0.
"""

from __future__ import annotations

import json
from typing import Any

from fastmcp import Context, FastMCP
from pydantic import Field

from gnani_mcp.tools._common import (
    DEFAULT_STT_MODEL,
    SttModel,
    build_v3_context,
    guess_audio_mime,
    json_field,
    normalize_stt_language,
    ready_ctx,
    require_upload_filename,
    resolve_file_input,
    validate_stt_format,
)

_STT_PATH = "/stt/v3"


def register(mcp: FastMCP) -> None:
    """Register all STT tools onto *mcp*."""

    @mcp.tool(
        name="gnani_stt_transcribe",
        description=(
            "Transcribe a short audio clip (≤ 30 s) using the Gnani Prisma Speech-to-Text API. "
            "For longer audio use ``gnani_stt_batch_transcribe``.\n\n"
            "**Models:**\n"
            "- ``prisma-v2.5`` (default) — you choose one language; supports ``verbatim`` / "
            "``transcribe`` (ITN) output and find-and-replace substitution.\n"
            "- ``prisma-v3.0`` — one model for all 10 languages. ``language_code`` may be "
            "``indic-auto`` (the model identifies the language) or 1–4 comma-separated codes "
            "like ``hi-IN,en-IN`` (hints, not a lock — the transcript follows the language "
            "actually spoken). Adds ``codemix`` and ``transliterate`` (Latin-letter) output and "
            "context hints: ``keyterms``, ``topic``, ``previous_text``, ``speaker_names``. "
            "The result includes ``detected_language_code``.\n\n"
            "**Languages:** Bengali (bn-IN), English India (en-IN), Gujarati (gu-IN), "
            "Hindi (hi-IN), Kannada (kn-IN), Malayalam (ml-IN), Marathi (mr-IN), Punjabi (pa-IN), "
            "Tamil (ta-IN), Telugu (te-IN).\n\n"
            "**Formats:** WAV, MP3, OGG, FLAC, AAC, M4A.\n\n"
            "**Output ``format``:** ``verbatim`` — numbers spelled out, English words in native "
            "script. ``transcribe`` — digits/currency/dates in conventional form (ITN on v2.5). "
            "v3.0 only: ``codemix`` — English words stay Latin, numbers mostly as words; "
            "``transliterate`` — whole transcript in Latin letters (``language_code`` optional). "
            "When ``format`` is omitted: v2.5 uses ``verbatim``; v3.0 picks ``transcribe`` for a "
            "single ``hi-IN``/``en-IN`` and ``verbatim`` otherwise — pass ``format`` explicitly "
            "to keep output stable when moving from v2.5 to v3.0.\n\n"
            "Use ``enable_substitution=True`` with a ``substitution_map`` to apply "
            "find-and-replace rules on the final transcript (max 10 rules)."
        ),
    )
    async def gnani_stt_transcribe(
        ctx: Context,
        language_code: str | None = Field(
            default=None,
            description=(
                "Language of the audio. prisma-v2.5: exactly one of bn-IN, en-IN, gu-IN, hi-IN, "
                "kn-IN, ml-IN, mr-IN, pa-IN, ta-IN, te-IN. prisma-v3.0: 'indic-auto', or 1–4 "
                "comma-separated codes (e.g. 'hi-IN,en-IN'). Required, except with "
                "model='prisma-v3.0' and format='transliterate'."
            ),
        ),
        audio_path: str | None = Field(
            default=None,
            description="Absolute local path to the audio file (e.g. '/home/user/call.wav').",
        ),
        audio_base64: str | None = Field(
            default=None,
            description="Base64-encoded audio data. Requires ``filename`` (with extension).",
        ),
        audio_url: str | None = Field(
            default=None,
            description=(
                "HTTP/HTTPS URL that points directly at the audio file. "
                "Requires ``filename`` (with extension)."
            ),
        ),
        filename: str | None = Field(
            default=None,
            description=(
                "File name including extension (e.g. 'recording.wav'). REQUIRED with "
                "``audio_base64`` or ``audio_url`` — the API chooses its decoder from the "
                "extension and rejects uploads without one. Not inferred from the URL. "
                "Supported: wav, mp3, ogg, flac, m4a, aac. Ignored with ``audio_path``."
            ),
        ),
        model: SttModel = Field(
            default=DEFAULT_STT_MODEL,
            description="'prisma-v2.5' (default) or 'prisma-v3.0'.",
        ),
        format: str | None = Field(
            default=None,
            description=(
                "Output style. 'verbatim' | 'transcribe' (both models); 'codemix' | "
                "'transliterate' (prisma-v3.0 only). Omit for the model default "
                "(v2.5: verbatim; v3.0: depends on language — see tool description)."
            ),
        ),
        itn_native_numerals: bool = Field(
            default=False,
            description=(
                "prisma-v2.5 only. When format='transcribe', set True to render digits in the "
                "native script of the target language (e.g. ₹५,००० instead of ₹5,000 for Hindi). "
                "No effect on prisma-v3.0 or with format='verbatim'."
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
        keyterms: list[str] | None = Field(
            default=None,
            description=(
                "prisma-v3.0 only. Words or short phrases to favour — names, brands, product "
                "terms (up to 200, any script). Compare results with and without hints."
            ),
        ),
        topic: str | None = Field(
            default=None,
            description="prisma-v3.0 only. A sentence or paragraph about the recording (≤ 1,600 chars).",
        ),
        previous_text: str | None = Field(
            default=None,
            description=(
                "prisma-v3.0 only. Transcript of the clip just before this one, for recordings "
                "cut into pieces (the last 600 characters are used)."
            ),
        ),
        speaker_names: list[str] | None = Field(
            default=None,
            description=(
                "prisma-v3.0 only. 1–4 names that may be spoken, to help spell them correctly. "
                "Not diarization."
            ),
        ),
        request_id: str | None = Field(
            default=None,
            description="Optional correlation ID for this request (useful for support / logging).",
        ),
    ) -> dict[str, Any]:
        sc = await ready_ctx(ctx)

        fmt = validate_stt_format(format, model)
        lang = normalize_stt_language(
            language_code,
            model,
            optional=(model == "prisma-v3.0" and fmt == "transliterate"),
        )
        context = build_v3_context(
            model=model,
            keyterms=keyterms,
            topic=topic,
            previous_text=previous_text,
            speaker_names=speaker_names,
        )

        require_upload_filename(
            file_path=audio_path, file_base64=audio_base64, file_url=audio_url, filename=filename
        )
        async with resolve_file_input(
            file_path=audio_path,
            file_base64=audio_base64,
            file_url=audio_url,
            filename=filename,
        ) as path:
            form_data = _build_form_data(
                language_code=lang,
                fmt=fmt,
                itn_native_numerals=itn_native_numerals,
                enable_substitution=enable_substitution,
                substitution_map=substitution_map,
                request_id=request_id,
                model=model,
                context=context,
            )

            with path.open("rb") as fh:
                files = {"audio_file": (path.name, fh, guess_audio_mime(path))}
                payload = await sc.client.post_multipart(
                    _STT_PATH, data=form_data, files=files
                )

        result: dict[str, Any] = {
            "success": payload.get("success", True),
            "transcript": payload.get("transcript", ""),
            "model": payload.get("model", model),
            "request_id": payload.get("request_id"),
        }
        # Optional fields — only present on some model/response combinations.
        for key in ("detected_language_code", "timestamp", "truncated"):
            if payload.get(key) is not None:
                result[key] = payload[key]
        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_form_data(
    *,
    language_code: str | None,
    fmt: str | None,
    itn_native_numerals: bool,
    enable_substitution: bool,
    substitution_map: list[dict[str, Any]] | None,
    request_id: str | None,
    model: str = DEFAULT_STT_MODEL,
    context: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build the ``multipart/form-data`` field dict for the STT endpoint.

    Prisma v2.5 requests stay byte-for-byte what they were before v3.0 support
    (no ``model`` field; ``format`` defaults to ``verbatim``). For v3.0, ``format``
    is only sent when explicitly chosen so the API can pick its per-request default.
    """
    is_v3 = model == "prisma-v3.0"
    data: dict[str, str] = {
        "enable_substitution": str(enable_substitution).lower(),
    }
    if language_code:
        data["language_code"] = language_code

    if is_v3:
        data["model"] = model
        if fmt is not None:
            data["format"] = fmt
        # itn_native_numerals has no effect on prisma-v3.0 — don't send it.
    else:
        data["format"] = fmt or "verbatim"
        data["itn_native_numerals"] = str(itn_native_numerals).lower()

    if substitution_map is not None and enable_substitution:
        data["substitution_map"] = json.dumps(substitution_map)
    if request_id is not None:
        data["request_id"] = request_id

    for key, value in (context or {}).items():
        data[key] = json_field(value) if isinstance(value, list) else value
    return data
