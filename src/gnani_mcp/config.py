"""Configuration: env-var resolution with ~/.gnani/credentials fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

OutputMode = Literal["files", "resources", "both"]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://api.vachana.ai"
DEFAULT_BASE_PATH = "~/Desktop"
DEFAULT_OUTPUT_MODE: OutputMode = "files"

_VALID_OUTPUT_MODES = frozenset({"files", "resources", "both"})


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration. Built exactly once at server startup."""

    api_key: str | None = None
    base_url: str = DEFAULT_BASE_URL
    base_path: Path = field(default_factory=lambda: Path(DEFAULT_BASE_PATH).expanduser())
    output_mode: OutputMode = DEFAULT_OUTPUT_MODE

    @classmethod
    def load(cls) -> "Config":
        """Resolve config from env vars, falling back to ~/.gnani/credentials."""
        creds = _read_credentials_file()

        api_key = os.environ.get("GNANI_API_KEY") or creds.get("api_key")
        base_url = os.environ.get("GNANI_API_BASE_URL", DEFAULT_BASE_URL)
        base_path_str = os.environ.get("GNANI_MCP_BASE_PATH", DEFAULT_BASE_PATH)
        mode_str = os.environ.get("GNANI_AUDIO_OUTPUT_MODE", DEFAULT_OUTPUT_MODE).lower()

        if mode_str not in _VALID_OUTPUT_MODES:
            raise ValueError(
                f"GNANI_AUDIO_OUTPUT_MODE must be one of {sorted(_VALID_OUTPUT_MODES)!r}; "
                f"got {mode_str!r}"
            )

        return cls(
            api_key=api_key,
            base_url=base_url.rstrip("/"),
            base_path=Path(base_path_str).expanduser(),
            output_mode=mode_str,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Credentials file helper
# ---------------------------------------------------------------------------


def _read_credentials_file() -> dict[str, str]:
    """Parse ``~/.gnani/credentials`` (simple ``key = value`` format).

    Returns an empty dict when the file is missing or unreadable.
    """
    path = Path("~/.gnani/credentials").expanduser()
    if not path.exists():
        return {}

    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out
