"""Audio output sink — writes synthesized audio to disk with timestamped filenames."""

from __future__ import annotations

import datetime
import logging
import struct
from pathlib import Path

logger = logging.getLogger("gnani_mcp.audio")


_UNKNOWN_SIZE = 0xFFFFFFFF


def fix_wav_header(data: bytes) -> bytes:
    """Return *data* with a correct RIFF/``data`` chunk size in the WAV header.

    The TTS API streams audio, so it doesn't know the total length up front and
    writes ``0xFFFFFFFF`` for the RIFF size and the ``data`` chunk size. Players
    read to end-of-file and cope, but programs that trust the header (Python's
    ``wave``, some editors) report a duration of many hours.

    Only fixes what is wrong: a ``data`` size that is the placeholder or larger
    than the bytes actually present, and a RIFF size that doesn't match the file.
    Anything that isn't a parseable RIFF/WAVE file — and files whose header is
    already correct — are returned unchanged.
    """
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return data

    off = 12
    while off + 8 <= len(data):
        chunk_id = data[off : off + 4]
        (size,) = struct.unpack_from("<I", data, off + 4)
        body = off + 8
        if chunk_id == b"data":
            remaining = len(data) - body
            if size != _UNKNOWN_SIZE and size <= remaining:
                new_data_size = size  # header is already plausible
            else:
                new_data_size = remaining
            out = bytearray(data)
            struct.pack_into("<I", out, off + 4, new_data_size)
            struct.pack_into("<I", out, 4, len(data) - 8)
            return bytes(out)
        if size == _UNKNOWN_SIZE:
            return data  # can't walk past a chunk of unknown length
        off = body + size + (size & 1)  # chunks are word-aligned
    return data


class AudioSink:
    """Save raw audio bytes to a configured base directory.

    WAV output gets its header sizes corrected (see :func:`fix_wav_header`).
    The sink creates the directory on first use.  Each file is written with a
    timestamp suffix so repeated calls never overwrite earlier results.

    Args:
        base_path: Directory where audio files will be saved.
    """

    def __init__(self, base_path: Path) -> None:
        self.base_path = base_path

    def save(
        self,
        audio_bytes: bytes,
        *,
        extension: str = "wav",
        stem: str = "audio",
    ) -> Path:
        """Write *audio_bytes* to a new file and return its absolute path.

        The filename follows the pattern ``gnani_<stem>_<YYYYMMDD_HHMMSS_ffffff>.<ext>``.
        """
        self.base_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"gnani_{stem}_{ts}.{extension.lstrip('.')}"
        out_path = self.base_path / filename
        if extension.lstrip(".").lower() == "wav":
            audio_bytes = fix_wav_header(audio_bytes)
        out_path.write_bytes(audio_bytes)
        logger.debug("Saved %d bytes → %s", len(audio_bytes), out_path)
        return out_path


def build_sink(base_path: Path) -> AudioSink:
    """Factory used by the server lifespan to create the shared AudioSink."""
    return AudioSink(base_path)
