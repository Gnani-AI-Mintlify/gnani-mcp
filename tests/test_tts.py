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
