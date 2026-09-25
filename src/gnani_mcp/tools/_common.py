"""Shared types, enums, and helpers used across all tool modules."""

from __future__ import annotations

import base64
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
from fastmcp import Context

from gnani_mcp._registry import ServerContext

# ---------------------------------------------------------------------------
# File size limit
# ---------------------------------------------------------------------------

MAX_FILE_BYTES = 25 * 1024 * 1024  # 25 MB

# ---------------------------------------------------------------------------
# Language codes — Gnani Prisma v2.5 STT
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
# TTS voice names — Gnani Timbre v2.5 (42 voices)
# ---------------------------------------------------------------------------

TtsVoice = Literal[
    # English
    "Kaveri", "Trupti", "Devika", "Pranav", "Shlok", "Girish",
    # Hindi
    "Nalini", "Bhavna", "Yashvi", "Urmila", "Jwala", "Chitra",
    "Ambuja", "Deepak", "Roopesh", "Vikrant", "Hemraj", "Jalaj", "Omkar",
    # Hinglish
    "Poorvi",
    # Tamil
    "Asmita", "Trisha", "Brinda", "Vedika", "Noopur",
    # Telugu
    "Suhana", "Lehara", "Lavanya", "Yukti", "Varuni",
    # Kannada
    "Saanvi", "Kavin",
    # Malayalam
    "Reshma", "Riyaan",
    # Marathi
    "Zahira", "Ishaan",
    # Bengali
    "Kirra", "Dhruva",
    # Gujarati
    "Falak", "Veera",
    # Punjabi
    "Mehuli", "Zayan",
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
