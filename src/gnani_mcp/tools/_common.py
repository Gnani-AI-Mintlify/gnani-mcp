"""Shared types, enums, and helpers used across all tool modules."""

from __future__ import annotations

import base64
import json
import struct
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, NamedTuple, get_args
from urllib.parse import urlsplit

import httpx
from fastmcp import Context

from gnani_mcp._registry import ServerContext
from gnani_mcp.audio import detect_audio_container, detect_sample_rate

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

# G.711 telephony audio (mu-law / A-law) is always produced at 8 kHz by the API,
# whatever ``sample_rate`` was requested — and it is triggered by *either* the
# container or the encoding (e.g. container=wav + encoding=pcm_mulaw is G.711 too).
_G711_CONTAINERS = frozenset({"mulaw", "alaw"})
_G711_ENCODINGS = frozenset({"pcm_mulaw", "pcm_alaw"})
G711_SAMPLE_RATE = 8_000


def resolve_sample_rate(
    audio_bytes: bytes, requested: int, container: str, encoding: str
) -> tuple[int, str | None]:
    """Return ``(real_rate, warning)`` for a synthesis response.

    The file is the source of truth: WAV, MP3 and OGG files declare their own sample
    rate, and the API does not always honour the request (e.g. an MP3 at 32 kbps comes
    back at 22,050 Hz whatever rate was asked for).  Headerless audio carries no
    rate, so there :func:`effective_sample_rate` applies — G.711 is always 8 kHz.
    """
    declared = detect_sample_rate(audio_bytes)
    if declared is None:
        return effective_sample_rate(requested, container, encoding)
    if declared == requested:
        return declared, None
    return declared, (
        f"sample_rate={requested} was requested, but the returned file is {declared} Hz "
        "(the API did not honour the requested rate). The returned sample_rate is the real one."
    )


class OutputFormat(NamedTuple):
    """What a synthesis response really contains, and how to save it."""

    extension: str  # file extension to save under
    container: str  # the real container: wav, mp3, ogg, raw, mulaw or alaw
    encoding: str  # how the samples are stored: linear_pcm, pcm_mulaw, pcm_alaw, oggopus or mp3
    warning: str | None  # set when this differs from the requested container


# WAV ``fmt `` chunk format tags that map onto our encoding names.
_WAV_FORMAT_TAGS = {1: "linear_pcm", 6: "pcm_alaw", 7: "pcm_mulaw"}


def _wav_encoding(data: bytes) -> str:
    """Encoding declared by a WAV header (falls back to linear_pcm)."""
    if len(data) >= 22:
        (tag,) = struct.unpack_from("<H", data, 20)
        return _WAV_FORMAT_TAGS.get(tag, "linear_pcm")
    return "linear_pcm"


def classify_output(audio_bytes: bytes, container: str, encoding: str) -> OutputFormat:
    """Decide the real format of a synthesis response.

    The API does not always return the *container* that was requested: when the
    container and encoding disagree it may return a different format (e.g.
    ``container=wav`` + ``encoding=pcm_mulaw`` gives headerless mu-law bytes, and
    ``container=wav`` + ``encoding=oggopus`` gives an OGG file).  The bytes are the
    source of truth, so file extension and reported container follow them.

    Headerless audio is always saved as ``.raw``.  When the bytes carry no
    recognisable header but the request was for wav/mp3/ogg with a non-G.711
    encoding, the request is trusted — we never rename on a mere guess.
    """
    detected = detect_audio_container(audio_bytes)
    if detected is not None:
        real, ext = detected, detected
    elif container in ("raw", "mulaw", "alaw"):
        real, ext = container, "raw"
    elif encoding in _G711_ENCODINGS:
        real, ext = ("mulaw" if encoding == "pcm_mulaw" else "alaw"), "raw"
    else:
        real, ext = container, container  # unrecognised bytes: trust the request

    # The sample encoding. Self-describing formats state it themselves; for
    # headerless audio only the request can tell us (G.711 is certain, anything
    # else is plain 16-bit PCM — a headerless file cannot be Opus or MP3).
    if detected == "wav":
        real_encoding = _wav_encoding(audio_bytes)
    elif real == "ogg":
        real_encoding = "oggopus"
    elif real == "mp3":
        real_encoding = "mp3"
    elif real == "mulaw" or encoding == "pcm_mulaw":
        real_encoding = "pcm_mulaw"
    elif real == "alaw" or encoding == "pcm_alaw":
        real_encoding = "pcm_alaw"
    elif encoding == "oggopus":  # asked for Opus but got headerless samples
        real_encoding = "linear_pcm"
    else:
        real_encoding = encoding

    warning = None
    if real != container:
        what = {
            "wav": "a WAV file",
            "ogg": "an OGG/Opus file",
            "mp3": "an MP3 file",
            "mulaw": "headerless mu-law (G.711) samples, 8000 Hz, with no file header",
            "alaw": "headerless A-law (G.711) samples, 8000 Hz, with no file header",
            "raw": "headerless raw samples with no file header",
        }[real]
        warning = (
            f"container='{container}' with encoding='{encoding}' was requested, but the API "
            f"returned {what}. Saved as .{ext} and reported as container='{real}'."
        )
    return OutputFormat(ext, real, real_encoding, warning)


def effective_sample_rate(
    requested: int, container: str, encoding: str
) -> tuple[int, str | None]:
    """Return ``(actual_rate, warning)`` for a synthesis request.

    Every container/encoding honours the requested ``sample_rate`` (verified for
    wav, raw, mp3 and ogg) except G.711, which the API always renders at 8 kHz.
    *warning* is set only when the requested rate was overridden.
    """
    if container in _G711_CONTAINERS or encoding in _G711_ENCODINGS:
        if requested == G711_SAMPLE_RATE:
            return G711_SAMPLE_RATE, None
        trigger = f"container='{container}'" if container in _G711_CONTAINERS else f"encoding='{encoding}'"
        return G711_SAMPLE_RATE, (
            f"sample_rate={requested} was ignored: {trigger} (G.711 telephony audio) is always "
            f"{G711_SAMPLE_RATE} Hz. The returned sample_rate is the real one."
        )
    return requested, None

# ---------------------------------------------------------------------------
# File input resolver
# ---------------------------------------------------------------------------


STT_SYNC_FORMATS = ("wav", "mp3", "ogg", "flac", "m4a", "aac")


def require_upload_filename(
    *,
    file_path: str | None,
    file_base64: str | None,
    file_url: str | None,
    filename: str | None,
) -> None:
    """Fail early when base64/URL audio is sent without a filename extension.

    The speech API chooses its decoder from the uploaded file's *extension*; an
    upload without one is rejected with a bare "Unsupported audio format".  For
    base64 and URL input the tool has no file name of its own, so the caller must
    supply it.  Nothing is inferred — a missing name is an error.
    """
    if file_path is not None or (file_base64 is None and file_url is None):
        return  # a local path carries its own name; "nothing given" is reported elsewhere
    source = "audio_base64" if file_base64 is not None else "audio_url"
    if not (filename and filename.strip()):
        problem = "was not given"
    elif not Path(filename.strip()).suffix:
        problem = f"({filename!r}) has no extension"
    else:
        return
    raise ValueError(
        f"`filename` {problem}. With {source} you must pass the file name including its "
        f"extension, e.g. 'call.wav': the speech API picks the decoder from the extension "
        f"and rejects an upload without one. Supported: {', '.join(STT_SYNC_FORMATS)}."
    )


def redact_url(url: str) -> str:
    """scheme://host/path only — query strings often hold signed-URL secrets."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}" if parts.scheme else "<invalid URL>"


# Content types that mean "the server answered with a web page / data, not audio".
_NON_AUDIO_TYPES = ("text/", "application/json", "application/xml", "application/xhtml+xml")


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
    # delete=False on purpose: the file is cleaned up in the ``finally`` block below.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)  # noqa: SIM115
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
            shown = redact_url(file_url)
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as dl:  # noqa: SIM117
                    async with dl.stream("GET", file_url) as resp:
                        if not resp.is_success:  # also catches un-followed redirects (3xx)
                            raise ValueError(
                                f"Could not download audio_url {shown}: the server answered "
                                f"HTTP {resp.status_code} {resp.reason_phrase}."
                            )
                        media_type = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                        if media_type.startswith(_NON_AUDIO_TYPES):
                            raise ValueError(
                                f"audio_url {shown} returned '{media_type}', not audio — "
                                "check that the link points directly at the audio file."
                            )
                        downloaded = 0
                        with tmp_path.open("wb") as fh:
                            async for chunk in resp.aiter_bytes(chunk_size=65_536):
                                downloaded += len(chunk)
                                if downloaded > max_bytes:
                                    raise ValueError(
                                        f"Download exceeded the {max_bytes:,}-byte limit."
                                    )
                                fh.write(chunk)
            except (httpx.TransportError, httpx.InvalidURL) as exc:
                # httpx messages can be empty (timeouts) — always name the error type.
                raise ValueError(
                    f"Could not download audio_url {shown}: {type(exc).__name__}"
                    + (f": {str(exc).rstrip('.')}" if str(exc) else "")
                    + "."
                ) from exc
        yield tmp_path
    finally:
        tmp.close()  # no-op if already closed; Windows can't delete a file that is still open
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
    v3_formats = _BATCH_V3_FORMATS if batch else _V3_FORMATS
    allowed = v3_formats if model == "prisma-v3.0" else _V25_FORMATS
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

    v25_max_codes = 3 if batch else 1
    max_codes = 4 if model == "prisma-v3.0" else v25_max_codes

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
                f"On Batch, topic must be {MIN_BATCH_TOPIC_CHARS}-{MAX_TOPIC_CHARS} "
                f"characters (got {len(t)})."
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
