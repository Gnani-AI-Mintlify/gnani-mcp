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
            # Keep the declared size when the header is already plausible.
            new_data_size = size if size != _UNKNOWN_SIZE and size <= remaining else remaining
            out = bytearray(data)
            struct.pack_into("<I", out, off + 4, new_data_size)
            struct.pack_into("<I", out, 4, len(data) - 8)
            return bytes(out)
        if size == _UNKNOWN_SIZE:
            return data  # can't walk past a chunk of unknown length
        off = body + size + (size & 1)  # chunks are word-aligned
    return data


# MPEG audio layer III tables, keyed by the frame header's MPEG-version bits
# (3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5).
_MP3_SAMPLE_RATES = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}
_MP3_BITRATES_KBPS = {
    3: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
    2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
    0: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),
}


def _mp3_frame(data: bytes, offset: int) -> tuple[int, int] | None:
    """``(frame_length_bytes, sample_rate)`` of the layer III frame at *offset*, else None."""
    if offset + 4 > len(data) or data[offset] != 0xFF or (data[offset + 1] & 0xE0) != 0xE0:
        return None
    version = (data[offset + 1] >> 3) & 3
    layer = (data[offset + 1] >> 1) & 3
    bitrate_idx = (data[offset + 2] >> 4) & 15
    rate_idx = (data[offset + 2] >> 2) & 3
    padding = (data[offset + 2] >> 1) & 1
    if version == 1 or layer != 1 or bitrate_idx in (0, 15) or rate_idx == 3:
        return None
    bitrate = _MP3_BITRATES_KBPS[version][bitrate_idx] * 1000
    rate = _MP3_SAMPLE_RATES[version][rate_idx]
    samples_per_frame_div = 144 if version == 3 else 72
    return samples_per_frame_div * bitrate // rate + padding, rate


def _mp3_frame_length(data: bytes, offset: int) -> int | None:
    """Length in bytes of the MPEG layer III frame at *offset*, or None if it isn't one."""
    frame = _mp3_frame(data, offset)
    return frame[0] if frame else None


def _looks_like_mp3(data: bytes) -> bool:
    # An ID3v2 tag: "ID3", a version byte 2-4, a revision byte.
    if data[:3] == b"ID3" and len(data) > 4 and data[3] in (2, 3, 4) and data[4] != 0xFF:
        return True
    # Otherwise demand a valid frame header *followed by another one*: a lone
    # 0xFF 0xEx pair can occur in raw PCM, two consistent frames cannot.
    length = _mp3_frame_length(data, 0)
    if length is None:
        return False
    if len(data) <= length + 4:
        return True  # a single-frame file
    return _mp3_frame_length(data, length) is not None


def detect_audio_container(data: bytes) -> str | None:
    """Identify an audio file by its leading bytes.

    Returns ``"wav"``, ``"ogg"`` or ``"mp3"``, or ``None`` when the bytes carry no
    recognisable header — i.e. headerless samples (raw PCM, mu-law, A-law), which
    cannot be told apart from each other by looking at them.
    """
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    if data[:4] == b"OggS":
        return "ogg"
    if _looks_like_mp3(data):
        return "mp3"
    return None


def _id3_tag_size(data: bytes) -> int:
    """Total size of a leading ID3v2 tag (header + body), or 0 if there is none."""
    if data[:3] != b"ID3" or len(data) < 10:
        return 0
    return 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))


def detect_sample_rate(data: bytes) -> int | None:
    """Sample rate the file itself declares, for the self-describing formats.

    * WAV  — the ``fmt `` chunk
    * MP3  — the first frame header
    * OGG  — the Opus header's original input rate (Opus always *plays* at 48 kHz;
      this is the rate the stream was encoded from)

    Returns ``None`` for headerless audio (which carries no rate) or an unreadable header.
    """
    kind = detect_audio_container(data)
    if kind == "wav":
        off = 12
        while off + 8 <= len(data):
            chunk_id = data[off : off + 4]
            (size,) = struct.unpack_from("<I", data, off + 4)
            if chunk_id == b"fmt " and off + 8 + 8 <= len(data):
                (rate,) = struct.unpack_from("<I", data, off + 8 + 4)
                return rate or None
            if size == _UNKNOWN_SIZE:
                return None
            off += 8 + size + (size & 1)
        return None
    if kind == "mp3":
        frame = _mp3_frame(data, _id3_tag_size(data))
        return frame[1] if frame else None
    if kind == "ogg":
        head = data.find(b"OpusHead", 0, 512)
        if head >= 0 and head + 16 <= len(data):
            (rate,) = struct.unpack_from("<I", data, head + 12)
            return rate or None
    return None


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
