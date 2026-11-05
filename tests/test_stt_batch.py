"""Tests for Batch STT config building."""

from __future__ import annotations

import pytest

from gnani_mcp.tools.stt_batch import _build_config

TOPIC = "Loan collection calls for a retail credit card portfolio"


def test_v25_config_is_unchanged() -> None:
    cfg = _build_config(model="prisma-v2.5", language_code="hi-IN,en-IN", with_diarization=True, num_speakers=2)
    assert cfg == {
        "model": "gnani-prisma-v2.5",
        "language_code": "hi-IN,en-IN",
        "mode": "transcribe",
        "with_diarization": True,
        "is_multi_channel": False,
        "with_denoise": False,
        "num_speakers": 2,
    }


def test_v3_config_with_context() -> None:
    cfg = _build_config(
        model="prisma-v3.0",
        language_code="auto",
        fmt="codemix",
        topic=TOPIC,
        keyterms=["EMI", "HDFC Bank"],
    )
    assert cfg["model"] == "prisma-v3.0"
    assert cfg["language_code"] == "indic-auto"
    assert cfg["format"] == "codemix"
    assert cfg["topic"] == TOPIC
    assert cfg["keyterms"] == ["EMI", "HDFC Bank"]


def test_format_refused_on_v25() -> None:
    with pytest.raises(ValueError, match="prisma-v3.0"):
        _build_config(model="prisma-v2.5", language_code="hi-IN", fmt="transcribe")


def test_context_refused_on_v25() -> None:
    with pytest.raises(ValueError, match="prisma-v3.0"):
        _build_config(model="prisma-v2.5", language_code="hi-IN", keyterms=["EMI"])


def test_v3_unsupported_combo() -> None:
    with pytest.raises(ValueError, match="only one of"):
        _build_config(model="prisma-v3.0", language_code="hi-IN", keyterms=["EMI"], speaker_names=["Priya"])


def test_v3_language_limit() -> None:
    with pytest.raises(ValueError, match="at most 4"):
        _build_config(model="prisma-v3.0", language_code="hi-IN,en-IN,ta-IN,te-IN,bn-IN")
