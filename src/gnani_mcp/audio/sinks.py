"""Audio output strategies — picked once at startup, injected into every tool.

Three strategies mirror Sarvam's design:

* ``FileSink``     — writes to disk under *base_path* (default ``~/Desktop``).
* ``ResourceSink`` — returns base64-encoded data; no disk I/O.  Ideal for
                     containerised or sandboxed deployments.
* ``BothSink``     — writes to disk *and* returns base64.  Maximum flexibility.

Select the strategy via the ``GNANI_AUDIO_OUTPUT_MODE`` env var
(``"files"`` | ``"resources"`` | ``"both"``).
"""

from __future__ import annotations

import base64
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gnani_mcp.config import OutputMode

logger = logging.getLogger("gnani_mcp.audio")


# ---------------------------------------------------------------------------
# Value object
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StoredAudio:
    """The result of writing audio through a sink.  Tools spread this into responses."""

    file_path: str | None
    resource_uri: str | None
    base64_data: str | None
    mime_type: str
    size_bytes: int


# ---------------------------------------------------------------------------
# Sink protocol
# ---------------------------------------------------------------------------


class AudioSink(Protocol):
    """Strategy for what to do with bytes emitted by a TTS / Voice Clone tool."""

    async def store(self, data: bytes, *, filename: str, mime_type: str) -> StoredAudio:
        ...


# ---------------------------------------------------------------------------
# Concrete sinks
# ---------------------------------------------------------------------------


class FileSink:
    """Write to disk under *base_path* and return the absolute file path."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = base_path

    async def store(self, data: bytes, *, filename: str, mime_type: str) -> StoredAudio:
        self._base_path.mkdir(parents=True, exist_ok=True)
        path = self._base_path / filename
        path.write_bytes(data)
        logger.debug("Saved %d bytes → %s", len(data), path)
        return StoredAudio(
            file_path=str(path),
            resource_uri=None,
            base64_data=None,
            mime_type=mime_type,
            size_bytes=len(data),
        )


class ResourceSink:
    """Return a base64-encoded resource — no disk I/O.

    Useful for containerised clients or sandboxed environments where the MCP
    server has no writable filesystem.
    """

    async def store(self, data: bytes, *, filename: str, mime_type: str) -> StoredAudio:
        return StoredAudio(
            file_path=None,
            resource_uri=f"gnani://audio/{filename}",
            base64_data=base64.b64encode(data).decode("ascii"),
            mime_type=mime_type,
            size_bytes=len(data),
        )


class BothSink:
    """Write to disk *and* return as base64 resource.  Maximum flexibility."""

    def __init__(self, base_path: Path) -> None:
        self._file_sink = FileSink(base_path)
        self._resource_sink = ResourceSink()

    async def store(self, data: bytes, *, filename: str, mime_type: str) -> StoredAudio:
        file_result = await self._file_sink.store(data, filename=filename, mime_type=mime_type)
        resource_result = await self._resource_sink.store(data, filename=filename, mime_type=mime_type)
        return StoredAudio(
            file_path=file_result.file_path,
            resource_uri=resource_result.resource_uri,
            base64_data=resource_result.base64_data,
            mime_type=mime_type,
            size_bytes=len(data),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_filename(stem: str, extension: str) -> str:
    """Generate a timestamped filename: ``gnani_{stem}_{YYYYMMDD_HHMMSS_ffffff}.{ext}``."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"gnani_{stem}_{ts}.{extension.lstrip('.')}"


def build_sink(mode: OutputMode, base_path: Path) -> AudioSink:
    """Construct the configured sink.  Called once at server startup."""
    if mode == "files":
        return FileSink(base_path)
    if mode == "resources":
        return ResourceSink()
    if mode == "both":
        return BothSink(base_path)
    raise ValueError(f"Unknown output mode: {mode!r}")
