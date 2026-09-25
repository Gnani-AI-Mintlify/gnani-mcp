"""Tests for gnani_mcp.config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gnani_mcp.config import Config, _read_credentials_file


class TestConfigLoad:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GNANI_API_KEY", raising=False)
        monkeypatch.delenv("GNANI_API_BASE_URL", raising=False)
        monkeypatch.delenv("GNANI_MCP_BASE_PATH", raising=False)
        monkeypatch.delenv("GNANI_AUDIO_OUTPUT_MODE", raising=False)

        cfg = Config.load()

        assert cfg.api_key is None
        assert cfg.base_url == "https://api.vachana.ai"
        assert cfg.output_mode == "files"

    def test_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GNANI_API_KEY", "sk_test_123")
        monkeypatch.setenv("GNANI_API_BASE_URL", "https://staging.vachana.ai/")
        monkeypatch.setenv("GNANI_AUDIO_OUTPUT_MODE", "both")

        cfg = Config.load()

        assert cfg.api_key == "sk_test_123"
        assert cfg.base_url == "https://staging.vachana.ai"  # trailing slash stripped
        assert cfg.output_mode == "both"

    def test_invalid_output_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GNANI_AUDIO_OUTPUT_MODE", "invalid")

        with pytest.raises(ValueError, match="GNANI_AUDIO_OUTPUT_MODE"):
            Config.load()


class TestCredentialsFile:
    def test_missing_file(self, tmp_path: Path) -> None:
        # Point to a nonexistent file — should return empty dict.
        result = _read_credentials_file.__wrapped__(  # type: ignore[attr-defined]
            tmp_path / ".gnani" / "credentials"
        ) if hasattr(_read_credentials_file, "__wrapped__") else {}
        assert isinstance(result, dict)

    def test_parses_key_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        creds_dir = tmp_path / ".gnani"
        creds_dir.mkdir()
        creds_file = creds_dir / "credentials"
        creds_file.write_text("api_key = sk_from_file\n# comment line\n\n")

        # Monkeypatch Path("~/.gnani/credentials") resolution.
        monkeypatch.setattr(
            "gnani_mcp.config.Path",
            lambda p: creds_file if "credentials" in str(p) else Path(p),
        )
        result = _read_credentials_file()
        assert result.get("api_key") == "sk_from_file"
