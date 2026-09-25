"""Shared pytest fixtures for gnani-mcp tests."""

from __future__ import annotations

import pytest

from gnani_mcp.config import Config


@pytest.fixture
def sample_config() -> Config:
    """A minimal Config instance with a fake API key."""
    return Config(api_key="test-api-key-123")
