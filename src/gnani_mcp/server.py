"""FastMCP server entry point.

The ``gnani-mcp`` console script (and ``python -m gnani_mcp``) land here.

Usage
-----
Run the MCP server over stdio (default)::

    gnani-mcp

Print the MCP client config JSON and exit::

    gnani-mcp --print
    gnani-mcp --api-key=sk_... --print
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from gnani_mcp._registry import ServerContext
from gnani_mcp.audio import build_sink
from gnani_mcp.config import Config
from gnani_mcp.http import GnaniClient

logger = logging.getLogger("gnani_mcp")


# ---------------------------------------------------------------------------
# Lifespan — build shared resources once at startup, tear down at shutdown
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(_server: FastMCP) -> AsyncIterator[ServerContext]:
    """Construct and yield the shared ``ServerContext``; close client on exit."""
    from gnani_mcp import __version__

    config = Config.load()

    auth_status = (
        "configured"
        if config.api_key
        else "missing — set GNANI_API_KEY or ~/.gnani/credentials"
    )

    client = GnaniClient(base_url=config.base_url, api_key=config.api_key)
    audio_sink = build_sink(config.base_path)

    ctx = ServerContext(config=config, client=client, audio_sink=audio_sink)

    logger.info(
        "gnani-mcp ready · v%s · base_url=%s · output_path=%s · auth=%s",
        __version__,
        config.base_url,
        config.base_path,
        auth_status,
    )

    try:
        yield ctx
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def build_server() -> FastMCP:
    """Construct the FastMCP server with all Gnani tools registered."""
    mcp = FastMCP(
        name="gnani-mcp",
        instructions=(
            "Gnani AI MCP server — Speech-to-Text, Text-to-Speech, and Voice Clone "
            "for 10 Indian languages. All tools require GNANI_API_KEY to be set."
        ),
        lifespan=_lifespan,
    )

    from gnani_mcp.tools import stt, stt_batch, tts, voice_clone

    stt.register(mcp)
    stt_batch.register(mcp)
    tts.register(mcp)
    voice_clone.register(mcp)

    return mcp


# ---------------------------------------------------------------------------
# Config printer
# ---------------------------------------------------------------------------


def _print_config(api_key: str | None = None) -> None:
    """Print MCP client configuration JSON to stdout."""
    import json
    import shutil

    env: dict[str, str] = {}
    if api_key:
        env["GNANI_API_KEY"] = api_key

    use_uvx = shutil.which("uvx") is not None

    if use_uvx:
        config = {
            "mcpServers": {
                "gnani": {
                    "command": "uvx",
                    "args": ["gnani-mcp"],
                    **({"env": env} if env else {}),
                }
            }
        }
    else:
        config = {
            "mcpServers": {
                "gnani": {
                    "command": "python",
                    "args": ["-m", "gnani_mcp"],
                    **({"env": env} if env else {}),
                }
            }
        }

    print(json.dumps(config, indent=2))


# ---------------------------------------------------------------------------
# Console entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console entry point for ``gnani-mcp`` / ``uvx gnani-mcp``.

    Sub-commands
    ------------
    ``gnani-mcp``
        Run the MCP server over stdio (default mode).
    ``gnani-mcp --print``
        Print MCP client config JSON and exit.
    ``gnani-mcp --api-key=sk_... --print``
        Include the API key in the printed config.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="gnani-mcp",
        description=(
            "Gnani AI MCP server — Speech-to-Text, Text-to-Speech, and Voice Clone "
            "for Indian languages"
        ),
    )
    parser.add_argument(
        "--api-key",
        metavar="KEY",
        help="Gnani API key to embed in the printed config (only used with --print)",
    )
    parser.add_argument(
        "--print",
        dest="print_config",
        action="store_true",
        help="Print MCP client configuration JSON and exit",
    )

    args = parser.parse_args()

    if args.print_config:
        _print_config(args.api_key)
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        stream=sys.stderr,
    )

    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
