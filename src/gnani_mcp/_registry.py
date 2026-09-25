"""Shared server context — the bundle passed to every tool via FastMCP lifespan."""

from __future__ import annotations

from dataclasses import dataclass

from gnani_mcp.audio import AudioSink
from gnani_mcp.config import Config
from gnani_mcp.http import GnaniClient


@dataclass
class ServerContext:
    """Holds all shared, lifespan-managed resources.

    An instance is created once at server startup (in ``server.py``) and
    injected into every tool call via FastMCP's ``Context.request_context.lifespan_context``.
    """

    config: Config
    client: GnaniClient
    audio_sink: AudioSink
