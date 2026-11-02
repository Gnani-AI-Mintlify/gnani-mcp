"""Shared types, enums, and helpers used across all tool modules."""

from __future__ import annotations

import base64
import json
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, get_args

import httpx
from fastmcp import Context

from gnani_mcp._registry import ServerContext

# ---------------------------------------------------------------------------
# File size limit
# ---------------------------------------------------------------------------

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB

# ---------------------------------------------------------------------------
# STT models
# ---------------------------------------------------------------------------

SttModel = Literal["prisma-v2.5", "prisma-v3.0"]
DEFAULT_STT_MODEL: SttModel = "prisma-v2.5"

# ---------------------------------------------------------------------------
# Language codes — Gnani Prisma STT (same ten languages on v2.5 and v3.0)
# ---------------------------------------------------------------------------

SttLanguageCode = Literal[
    "bn-IN",  # Bengali
    "en-IN",  # English (India) — accepts Hinglish audio
    "gu-IN",  # Gujarati
    "hi-IN",  # Hindi
    "kn-IN",  # Kannada
    "ml-IN",  # Malayalam
    "mr-IN",  # Marathi
    "pa-IN",  # Punjabi
    "ta-IN",  # Tamil
    "te-IN",  # Telugu
]

# ---------------------------------------------------------------------------
# Language codes — Gnani Timbre v2.5 TTS
# ---------------------------------------------------------------------------

TtsLanguageCode = Literal[
    "auto",   # Auto-detect from script (recommended for mixed content)
    "bn-IN",  # Bengali
    "en-IN",  # English (India)
    "gu-IN",  # Gujarati
    "hi-IN",  # Hindi
    "hi-en",  # Hinglish (code-mixed Hindi–English)
    "kn-IN",  # Kannada
    "ml-IN",  # Malayalam
    "mr-IN",  # Marathi
    "pa-IN",  # Punjabi
    "ta-IN",  # Tamil
    "te-IN",  # Telugu
]

# ---------------------------------------------------------------------------
# Audio format types
# ---------------------------------------------------------------------------

AudioContainer = Literal["wav", "mp3", "ogg", "raw", "mulaw", "alaw"]
AudioEncoding = Literal["linear_pcm", "pcm_s16le", "pcm_mulaw", "pcm_alaw", "oggopus"]
MP3Bitrate = Literal["32k", "64k", "96k", "128k", "192k"]

# ---------------------------------------------------------------------------
# File input resolver
# ---------------------------------------------------------------------------


@asynccontextmanager
async def resolve_file_input(
    *,
    file_path: str | None = None,
    file_base64: str | None = None,
    file_url: str | None = None,
    filename: str | None = None,
    max_bytes: int = MAX_FILE_BYTES,
) -> AsyncIterator[Path]:
    """Resolve a file from a local path, base64 data, or URL into a ``Path``.

    Exactly one of ``file_path``, ``file_base64``, or ``file_url`` must be
    supplied.  For base64/URL inputs a temporary file is created and
    automatically deleted when the context manager exits.

    ``filename`` is used to preserve the file extension (required for MIME
    detection when the input is base64 or a URL).
    """
    provided = sum(x is not None for x in (file_path, file_base64, file_url))
    if provided == 0:
        raise ValueError(
            "Provide one of: file_path (local path), file_base64 (base64-encoded bytes), "
            "or file_url (HTTP/HTTPS URL)."
        )
    if provided > 1:
        raise ValueError(
            f"Provide exactly one of file_path, file_base64, or file_url — got {provided}."
        )

    if file_path is not None:
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")
        yield path
        return

    # Determine temp file suffix from optional filename hint.
    suffix = Path(filename).suffix if filename else ""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = Path(tmp.name)

    try:
        if file_base64 is not None:
            data = base64.b64decode(file_base64)
            if len(data) > max_bytes:
                raise ValueError(
                    f"Decoded file is {len(data):,} bytes; exceeds the {max_bytes:,}-byte limit."
                )
            tmp.write(data)
            tmp.close()
        else:
            assert file_url is not None
            tmp.close()  # close before writing via httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as dl:
                async with dl.stream("GET", file_url) as resp:
                    resp.raise_for_status()
                    downloaded = 0
                    with tmp_path.open("wb") as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=65_536):
                            downloaded += len(chunk)
                            if downloaded > max_bytes:
                                raise ValueError(
                                    f"Download exceeded the {max_bytes:,}-byte limit."
                                )
                            fh.write(chunk)
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# MIME type helper
# ---------------------------------------------------------------------------


def guess_audio_mime(path: Path) -> str:
    """Return the MIME type for a common audio file extension."""
    return {
        "wav": "audio/wav",
        "mp3": "audio/mpeg",
        "ogg": "audio/ogg",
        "flac": "audio/flac",
        "m4a": "audio/mp4",
        "aac": "audio/aac",
        "webm": "audio/webm",
        "opus": "audio/opus",
        "amr": "audio/amr",
    }.get(path.suffix.lower().lstrip("."), "application/octet-stream")


# ---------------------------------------------------------------------------
# Server context accessor
# ---------------------------------------------------------------------------


def get_server_ctx(ctx: Context) -> ServerContext:
    """Retrieve the lifespan-managed :class:`~gnani_mcp._registry.ServerContext`.

    Raises ``RuntimeError`` if the lifespan context is missing (indicates a
    server wiring bug).
    """
    lifespan = ctx.request_context.lifespan_context
    if not isinstance(lifespan, ServerContext):
        raise RuntimeError(
            "Lifespan context is not a ServerContext — server.py wiring is broken."
        )
    return lifespan


async def ready_ctx(ctx: Context) -> ServerContext:
    """Return the :class:`ServerContext` after verifying the API key is set.

    Every tool that calls the Gnani API should ``await`` this on its first
    line.  Raises :class:`~gnani_mcp.exceptions.AuthenticationError` when
    ``GNANI_API_KEY`` is not configured.
    """
    sc = get_server_ctx(ctx)
    if not sc.config.api_key:
        from gnani_mcp.exceptions import AuthenticationError

        raise AuthenticationError(
            "GNANI_API_KEY is not set. "
            "Add it to your MCP config (env.GNANI_API_KEY) or to ~/.gnani/credentials."
        )
    return sc


# ---------------------------------------------------------------------------
# STT request validation (language, output format, Prisma v3.0 context)
# ---------------------------------------------------------------------------

STT_LANGUAGE_CODES: frozenset[str] = frozenset(get_args(SttLanguageCode))

_V25_FORMATS = ("verbatim", "transcribe")
_V3_FORMATS = ("verbatim", "transcribe", "codemix", "transliterate")
_BATCH_V3_FORMATS = ("verbatim", "transcribe", "codemix")  # no transliterate on Batch

MAX_KEYTERMS = 200
MAX_TOPIC_CHARS = 1_600
MIN_BATCH_TOPIC_CHARS = 30
MAX_SPEAKER_NAMES = 4
_FORBIDDEN_MARKERS = ("<|", "|>")

# Batch accepts only these combinations of context fields.
_BATCH_CONTEXT_COMBOS: frozenset[frozenset[str]] = frozenset(
    {
        frozenset(),
        frozenset({"keyterms"}),
        frozenset({"topic"}),
        frozenset({"topic", "keyterms"}),
        frozenset({"speaker_names"}),
    }
)


def validate_stt_format(
    fmt: str | None, model: str, *, batch: bool = False
) -> str | None:
    """Validate the output ``format`` for *model*; returns it lower-cased (or None)."""
    if fmt is None:
        return None
    fmt = fmt.strip().lower()
    if model == "prisma-v3.0":
        allowed = _BATCH_V3_FORMATS if batch else _V3_FORMATS
    else:
        allowed = _V25_FORMATS
    if fmt not in allowed:
        extra = ""
        if fmt in _V3_FORMATS:
            where = "Batch" if (batch and fmt == "transliterate") else model
            extra = f" ({fmt!r} is not available on {where})"
        raise ValueError(
            f"Invalid format {fmt!r} for {model}{extra}. Allowed: {', '.join(allowed)}."
        )
    return fmt


def normalize_stt_language(
    language_code: str | None,
    model: str,
    *,
    batch: bool = False,
    optional: bool = False,
) -> str | None:
    """Validate and normalise ``language_code`` for *model*.

    * Prisma v2.5 — REST: exactly one code. Batch: 1–3 codes (language identified per file).
    * Prisma v3.0 — ``indic-auto`` (Batch also accepts ``auto``) or 1–4 distinct codes.

    Returns the comma-joined, whitespace-free string to send to the API, or
    ``None`` when *optional* is True and nothing was supplied.
    """
    raw = (language_code or "").strip()
    if not raw:
        if optional:
            return None
        raise ValueError(
            "language_code is required (e.g. 'hi-IN'). "
            "With model='prisma-v3.0' you can also pass 'indic-auto' or up to 4 comma-separated codes."
        )

    codes = [c.strip() for c in raw.split(",") if c.strip()]
    valid_list = ", ".join(sorted(STT_LANGUAGE_CODES))
    lowered = [c.lower() for c in codes]

    if any(c in ("indic-auto", "auto") for c in lowered):
        if model != "prisma-v3.0":
            raise ValueError(
                "Automatic language detection ('indic-auto') requires model='prisma-v3.0'."
            )
        if len(codes) != 1:
            raise ValueError("'indic-auto' cannot be combined with other language codes.")
        if lowered[0] == "auto" and not batch:
            raise ValueError("Use 'indic-auto' for automatic language detection.")
        return "indic-auto"

    if model == "prisma-v3.0":
        max_codes = 4
    else:
        max_codes = 3 if batch else 1

    if len(set(codes)) != len(codes):
        raise ValueError(f"Duplicate language codes in {raw!r}.")
    if len(codes) > max_codes:
        hint = " Use 'indic-auto' instead." if model == "prisma-v3.0" else ""
        raise ValueError(
            f"{model} accepts at most {max_codes} language code(s); got {len(codes)}.{hint}"
        )
    bad = [c for c in codes if c not in STT_LANGUAGE_CODES]
    if bad:
        raise ValueError(
            f"Unsupported language code(s): {', '.join(bad)}. Supported: {valid_list}."
        )
    return ",".join(codes)


def _check_markers(field_name: str, values: list[str]) -> None:
    for v in values:
        if any(m in v for m in _FORBIDDEN_MARKERS):
            raise ValueError(f"{field_name} must not contain '<|' or '|>'.")


def build_v3_context(
    *,
    model: str,
    keyterms: list[str] | None = None,
    topic: str | None = None,
    previous_text: str | None = None,
    speaker_names: list[str] | None = None,
    batch: bool = False,
) -> dict[str, Any]:
    """Validate Prisma v3.0 context hints; return the fields that were supplied.

    Raises ``ValueError`` when hints are sent with another model (the API refuses
    them on Batch and ignores/mishandles them on REST), when limits are exceeded,
    or — on Batch — when an unsupported combination is used.

    Values: ``keyterms`` / ``speaker_names`` → ``list[str]``; ``topic`` /
    ``previous_text`` → ``str``.
    """
    supplied: dict[str, Any] = {}

    if keyterms:
        cleaned = [k.strip() for k in keyterms if k and k.strip()]
        if len(cleaned) > MAX_KEYTERMS:
            raise ValueError(f"keyterms accepts at most {MAX_KEYTERMS} items (got {len(cleaned)}).")
        _check_markers("keyterms", cleaned)
        if cleaned:
            supplied["keyterms"] = cleaned
    if topic is not None and topic.strip():
        t = topic.strip()
        if len(t) > MAX_TOPIC_CHARS:
            raise ValueError(f"topic must be at most {MAX_TOPIC_CHARS} characters (got {len(t)}).")
        if batch and len(t) < MIN_BATCH_TOPIC_CHARS:
            raise ValueError(
                f"On Batch, topic must be {MIN_BATCH_TOPIC_CHARS}-{MAX_TOPIC_CHARS} characters (got {len(t)})."
            )
        _check_markers("topic", [t])
        supplied["topic"] = t
    if previous_text is not None and previous_text.strip():
        if batch:
            raise ValueError("previous_text is not available on Batch (REST only).")
        _check_markers("previous_text", [previous_text])
        supplied["previous_text"] = previous_text
    if speaker_names:
        names = [n.strip() for n in speaker_names if n and n.strip()]
        if not 1 <= len(names) <= MAX_SPEAKER_NAMES:
            raise ValueError(
                f"speaker_names accepts 1-{MAX_SPEAKER_NAMES} names (got {len(names)})."
            )
        if any("\n" in n or "\r" in n for n in names):
            raise ValueError("speaker_names must each be a single line.")
        _check_markers("speaker_names", names)
        supplied["speaker_names"] = names

    if supplied and model != "prisma-v3.0":
        raise ValueError(
            f"{', '.join(supplied)} {'is' if len(supplied) == 1 else 'are'} only supported "
            "with model='prisma-v3.0'."
        )
    if batch and frozenset(supplied) not in _BATCH_CONTEXT_COMBOS:
        raise ValueError(
            "On Batch, send only one of: keyterms, topic, topic + keyterms, or speaker_names "
            f"(got {', '.join(supplied)})."
        )
    return supplied


def json_field(value: Any) -> str:
    """JSON-encode a form field value, keeping non-ASCII text readable."""
    return json.dumps(value, ensure_ascii=False)
