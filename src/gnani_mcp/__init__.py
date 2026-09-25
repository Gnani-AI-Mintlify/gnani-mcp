"""Gnani AI MCP server — first-class MCP tools for Gnani Speech APIs (STT, TTS, Voice Clone)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("gnani-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
