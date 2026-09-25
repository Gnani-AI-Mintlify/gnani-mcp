"""Audio output sink — writes synthesized audio to disk with timestamped filenames."""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

logger = logging.getLogger("gnani_mcp.audio")


class AudioSink:
    """Save raw audio bytes to a configured base directory.

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
        out_path.write_bytes(audio_bytes)
        logger.debug("Saved %d bytes → %s", len(audio_bytes), out_path)
        return out_path


def build_sink(base_path: Path) -> AudioSink:
    """Factory used by the server lifespan to create the shared AudioSink."""
    return AudioSink(base_path)
