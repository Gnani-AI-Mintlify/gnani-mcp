"""Tests for the STT tool helpers."""

from __future__ import annotations

import json

from gnani_mcp.tools.stt import _build_form_data


class TestBuildFormData:
    def test_basic(self) -> None:
        data = _build_form_data(
            language_code="hi-IN",
            fmt="verbatim",
            itn_native_numerals=False,
            enable_substitution=False,
            substitution_map=None,
            request_id=None,
        )
        assert data["language_code"] == "hi-IN"
        assert data["format"] == "verbatim"
        assert data["itn_native_numerals"] == "false"
        assert data["enable_substitution"] == "false"
        assert "substitution_map" not in data
        assert "request_id" not in data

    def test_with_substitution(self) -> None:
        rules = [{"patterns": ["ok"], "replacement": "acknowledged"}]
        data = _build_form_data(
            language_code="en-IN",
            fmt="transcribe",
            itn_native_numerals=True,
            enable_substitution=True,
            substitution_map=rules,
            request_id="req-123",
        )
        assert data["format"] == "transcribe"
        assert data["itn_native_numerals"] == "true"
        assert data["enable_substitution"] == "true"
        assert json.loads(data["substitution_map"]) == rules
        assert data["request_id"] == "req-123"

    def test_substitution_map_ignored_when_disabled(self) -> None:
        rules = [{"patterns": ["ok"], "replacement": "acknowledged"}]
        data = _build_form_data(
            language_code="en-IN",
            fmt="transcribe",
            itn_native_numerals=False,
            enable_substitution=False,  # disabled
            substitution_map=rules,
            request_id=None,
        )
        # substitution_map should NOT be included when enable_substitution=False
        assert "substitution_map" not in data
