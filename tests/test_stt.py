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


# ---------------------------------------------------------------------------
# Prisma v3.0 support
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from gnani_mcp.tools._common import (  # noqa: E402
    build_v3_context,
    normalize_stt_language,
    validate_stt_format,
)


class TestBuildFormDataV3:
    def test_v25_form_is_unchanged(self) -> None:
        data = _build_form_data(
            language_code="hi-IN",
            fmt=None,
            itn_native_numerals=False,
            enable_substitution=False,
            substitution_map=None,
            request_id=None,
        )
        assert "model" not in data
        assert data["format"] == "verbatim"
        assert data["itn_native_numerals"] == "false"

    def test_v3_sends_model_and_omits_format_when_unset(self) -> None:
        data = _build_form_data(
            language_code="indic-auto",
            fmt=None,
            itn_native_numerals=True,
            enable_substitution=False,
            substitution_map=None,
            request_id=None,
            model="prisma-v3.0",
        )
        assert data["model"] == "prisma-v3.0"
        assert data["language_code"] == "indic-auto"
        assert "format" not in data
        assert "itn_native_numerals" not in data

    def test_v3_context_fields_are_encoded(self) -> None:
        data = _build_form_data(
            language_code="hi-IN",
            fmt="codemix",
            itn_native_numerals=False,
            enable_substitution=False,
            substitution_map=None,
            request_id=None,
            model="prisma-v3.0",
            context={
                "keyterms": ["खाता", "HDFC Bank"],
                "topic": "banking",
                "previous_text": "hello",
                "speaker_names": ["Priya"],
            },
        )
        assert data["format"] == "codemix"
        assert json.loads(data["keyterms"]) == ["खाता", "HDFC Bank"]
        assert "खाता" in data["keyterms"]  # not \u-escaped
        assert data["topic"] == "banking"
        assert data["previous_text"] == "hello"
        assert json.loads(data["speaker_names"]) == ["Priya"]

    def test_transliterate_without_language(self) -> None:
        data = _build_form_data(
            language_code=None,
            fmt="transliterate",
            itn_native_numerals=False,
            enable_substitution=False,
            substitution_map=None,
            request_id=None,
            model="prisma-v3.0",
        )
        assert "language_code" not in data


class TestNormalizeLanguage:
    def test_v25_single_code(self) -> None:
        assert normalize_stt_language("hi-IN", "prisma-v2.5") == "hi-IN"

    def test_v25_rejects_multiple_and_auto(self) -> None:
        with pytest.raises(ValueError, match="at most 1"):
            normalize_stt_language("hi-IN,en-IN", "prisma-v2.5")
        with pytest.raises(ValueError, match="prisma-v3.0"):
            normalize_stt_language("indic-auto", "prisma-v2.5")

    def test_v25_batch_allows_three(self) -> None:
        assert normalize_stt_language("hi-IN, en-IN,ta-IN", "prisma-v2.5", batch=True) == "hi-IN,en-IN,ta-IN"
        with pytest.raises(ValueError, match="at most 3"):
            normalize_stt_language("hi-IN,en-IN,ta-IN,te-IN", "prisma-v2.5", batch=True)

    def test_v3_auto_and_lists(self) -> None:
        assert normalize_stt_language("indic-auto", "prisma-v3.0") == "indic-auto"
        assert normalize_stt_language("hi-IN,en-IN", "prisma-v3.0") == "hi-IN,en-IN"
        assert normalize_stt_language("hi-IN,en-IN,ta-IN,te-IN", "prisma-v3.0")

    def test_v3_limits(self) -> None:
        with pytest.raises(ValueError, match="at most 4"):
            normalize_stt_language("hi-IN,en-IN,ta-IN,te-IN,bn-IN", "prisma-v3.0")
        with pytest.raises(ValueError, match="Duplicate"):
            normalize_stt_language("hi-IN,hi-IN", "prisma-v3.0")
        with pytest.raises(ValueError, match="combined"):
            normalize_stt_language("indic-auto,hi-IN", "prisma-v3.0")

    def test_auto_spelling_only_on_batch(self) -> None:
        assert normalize_stt_language("auto", "prisma-v3.0", batch=True) == "indic-auto"
        with pytest.raises(ValueError):
            normalize_stt_language("auto", "prisma-v3.0")

    def test_unsupported_code(self) -> None:
        with pytest.raises(ValueError, match="as-IN"):
            normalize_stt_language("as-IN", "prisma-v3.0")

    def test_missing(self) -> None:
        with pytest.raises(ValueError, match="required"):
            normalize_stt_language(None, "prisma-v3.0")
        assert normalize_stt_language("", "prisma-v3.0", optional=True) is None


class TestValidateFormat:
    def test_defaults(self) -> None:
        assert validate_stt_format(None, "prisma-v3.0") is None
        assert validate_stt_format("Verbatim", "prisma-v2.5") == "verbatim"

    def test_v3_only_styles(self) -> None:
        assert validate_stt_format("codemix", "prisma-v3.0") == "codemix"
        assert validate_stt_format("transliterate", "prisma-v3.0") == "transliterate"
        with pytest.raises(ValueError, match="codemix"):
            validate_stt_format("codemix", "prisma-v2.5")

    def test_transliterate_not_on_batch(self) -> None:
        with pytest.raises(ValueError, match="Batch"):
            validate_stt_format("transliterate", "prisma-v3.0", batch=True)


class TestBuildV3Context:
    def test_empty(self) -> None:
        assert build_v3_context(model="prisma-v2.5") == {}

    def test_rejected_on_v25(self) -> None:
        with pytest.raises(ValueError, match="prisma-v3.0"):
            build_v3_context(model="prisma-v2.5", keyterms=["EMI"])

    def test_rest_allows_any_combination(self) -> None:
        ctx = build_v3_context(
            model="prisma-v3.0",
            keyterms=["EMI"],
            topic="a call",
            previous_text="earlier",
            speaker_names=["Priya", "Rahul"],
        )
        assert set(ctx) == {"keyterms", "topic", "previous_text", "speaker_names"}

    def test_limits(self) -> None:
        with pytest.raises(ValueError, match="200"):
            build_v3_context(model="prisma-v3.0", keyterms=[f"w{i}" for i in range(201)])
        with pytest.raises(ValueError, match="1600"):
            build_v3_context(model="prisma-v3.0", topic="x" * 1601)
        with pytest.raises(ValueError, match="1-4"):
            build_v3_context(model="prisma-v3.0", speaker_names=list("abcde"))
        with pytest.raises(ValueError, match="single line"):
            build_v3_context(model="prisma-v3.0", speaker_names=["a\nb"])
        with pytest.raises(ValueError, match=r"<\|"):
            build_v3_context(model="prisma-v3.0", keyterms=["bad <| thing"])

    def test_batch_topic_minimum_and_no_previous_text(self) -> None:
        with pytest.raises(ValueError, match="30-1600"):
            build_v3_context(model="prisma-v3.0", topic="too short", batch=True)
        with pytest.raises(ValueError, match="REST only"):
            build_v3_context(model="prisma-v3.0", previous_text="earlier", batch=True)

    def test_batch_combinations(self) -> None:
        topic = "Loan collection calls for a retail credit card portfolio"
        assert build_v3_context(model="prisma-v3.0", topic=topic, keyterms=["EMI"], batch=True)
        assert build_v3_context(model="prisma-v3.0", speaker_names=["Priya"], batch=True)
        with pytest.raises(ValueError, match="only one of"):
            build_v3_context(model="prisma-v3.0", keyterms=["EMI"], speaker_names=["Priya"], batch=True)
