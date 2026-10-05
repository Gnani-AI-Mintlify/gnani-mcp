"""Audio output strategies for the Gnani MCP server."""

from gnani_mcp.audio.sinks import (
    AudioSink,
    BothSink,
    FileSink,
    ResourceSink,
    StoredAudio,
    build_sink,
    make_filename,
)

__all__ = [
    "AudioSink",
    "BothSink",
    "FileSink",
    "ResourceSink",
    "StoredAudio",
    "build_sink",
    "make_filename",
]
