"""Tests for TTS helpers."""

from __future__ import annotations

from gnani_mcp.tools.tts import _VOICE_CATALOG


class TestVoiceCatalog:
    def test_catalog_has_42_voices(self) -> None:
        assert len(_VOICE_CATALOG) == 42

    def test_all_voices_have_required_fields(self) -> None:
        required = {"voice", "gender", "language", "persona", "description"}
        for entry in _VOICE_CATALOG:
            assert required <= entry.keys(), f"Missing fields in: {entry}"

    def test_no_duplicate_voice_names(self) -> None:
        names = [v["voice"] for v in _VOICE_CATALOG]
        assert len(names) == len(set(names)), "Duplicate voice names found"

    def test_gender_values(self) -> None:
        genders = {v["gender"] for v in _VOICE_CATALOG}
        assert genders <= {"Male", "Female"}

    def test_all_languages_covered(self) -> None:
        languages = {v["language"] for v in _VOICE_CATALOG}
        expected = {"en-IN", "hi-IN", "hi-en", "ta-IN", "te-IN", "kn-IN", "ml-IN", "mr-IN", "bn-IN", "gu-IN", "pa-IN"}
        assert expected == languages


# ---------------------------------------------------------------------------
# Timbre v3.0 support
# ---------------------------------------------------------------------------

import pytest  # noqa: E402

from gnani_mcp.tools.tts import build_tts_warnings  # noqa: E402
from gnani_mcp.voices import (  # noqa: E402
    AUDIO_TAGS,
    VOICE_CATALOG_V3,
    VOICE_CATALOG_V25,
    get_catalog,
    inspect_audio_tags,
    resolve_voice,
)


class TestV3Catalog:
    def test_has_13_voices(self) -> None:
        assert len(VOICE_CATALOG_V3) == 13

    def test_gender_split(self) -> None:
        females = [v for v in VOICE_CATALOG_V3 if v["gender"] == "Female"]
        assert len(females) == 7
        assert len(VOICE_CATALOG_V3) - len(females) == 6

    def test_no_overlap_with_v25(self) -> None:
        v3 = {v["voice"] for v in VOICE_CATALOG_V3}
        v25 = {v["voice"] for v in VOICE_CATALOG_V25}
        assert not v3 & v25

    def test_required_fields(self) -> None:
        for entry in VOICE_CATALOG_V3:
            assert {"voice", "gender", "language", "persona", "description"} <= entry.keys()

    def test_get_catalog(self) -> None:
        assert get_catalog("timbre-v2.5") is VOICE_CATALOG_V25
        assert get_catalog("timbre-v3.0") is VOICE_CATALOG_V3
        with pytest.raises(ValueError):
            get_catalog("timbre-v9")


class TestResolveVoice:
    def test_canonicalises_case(self) -> None:
        assert resolve_voice("timbre-v3.0", "shivani") == "Shivani"
        assert resolve_voice("timbre-v2.5", " NALINI ") == "Nalini"

    def test_wrong_model_hints_correct_one(self) -> None:
        with pytest.raises(ValueError, match="timbre-v3.0"):
            resolve_voice("timbre-v2.5", "Shivani")
        with pytest.raises(ValueError, match="timbre-v2.5"):
            resolve_voice("timbre-v3.0", "Nalini")

    def test_unknown_voice(self) -> None:
        with pytest.raises(ValueError, match="Valid voices"):
            resolve_voice("timbre-v3.0", "Nobody")


class TestAudioTags:
    def test_thirteen_tags(self) -> None:
        assert len(AUDIO_TAGS) == 13

    def test_inspect(self) -> None:
        known, unknown = inspect_audio_tags("Hi <laugh> there <clears throat> <bogus> <laugh>")
        assert known == ["laugh", "clears throat"]
        assert unknown == ["bogus"]

    def test_warns_when_tags_on_v25(self) -> None:
        warnings = build_tts_warnings("timbre-v2.5", "Hello <pauses> world")
        assert len(warnings) == 1
        assert "timbre-v3.0" in warnings[0]

    def test_no_warning_for_valid_v3(self) -> None:
        assert build_tts_warnings("timbre-v3.0", "Hello <pauses> world") == []

    def test_warns_on_unknown_tag_v3(self) -> None:
        warnings = build_tts_warnings("timbre-v3.0", "Hello <Laughs Harder> world")
        assert len(warnings) == 1
        assert "stripped" in warnings[0]

    def test_plain_text_never_warns(self) -> None:
        assert build_tts_warnings("timbre-v2.5", "No tags here") == []
