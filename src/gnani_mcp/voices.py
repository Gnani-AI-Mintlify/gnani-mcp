"""Static TTS voice catalogs and audio-tag helpers.

Source: https://docs.gnani.ai/api/TTS/available-voices.md
Voices are NOT interchangeable between models — a voice only works with the
model whose catalog lists it.
"""

from __future__ import annotations

import re
from typing import Literal

TtsModel = Literal["timbre-v2.5", "timbre-v3.0"]
DEFAULT_TTS_MODEL: TtsModel = "timbre-v2.5"

# ---------------------------------------------------------------------------
# Timbre v2.5 — 42 voices, one preferred language each
# ---------------------------------------------------------------------------

VOICE_CATALOG_V25: list[dict[str, str]] = [
    {"voice": "Ambuja",  "gender": "Female", "language": "hi-IN", "persona": "Professional",          "description": "Clear, composed virtual assistant"},
    {"voice": "Asmita",  "gender": "Female", "language": "ta-IN", "persona": "Professional",          "description": "Polished, refined, smooth corporate voice"},
    {"voice": "Bhavna",  "gender": "Female", "language": "hi-IN", "persona": "Friendly",              "description": "Friendly voice for customer support"},
    {"voice": "Brinda",  "gender": "Female", "language": "ta-IN", "persona": "Professional",          "description": "Steady, even-paced professional voice"},
    {"voice": "Chitra",  "gender": "Female", "language": "hi-IN", "persona": "Warm, empathetic",      "description": "Mature voice for customer care"},
    {"voice": "Deepak",  "gender": "Male",   "language": "hi-IN", "persona": "Professional",          "description": "Clear, measured voice for corporate use"},
    {"voice": "Devika",  "gender": "Female", "language": "en-IN", "persona": "Professional",          "description": "Authoritative voice for customer support"},
    {"voice": "Dhruva",  "gender": "Male",   "language": "bn-IN", "persona": "Conversational",        "description": "Casual, relatable voice for conversations"},
    {"voice": "Falak",   "gender": "Female", "language": "gu-IN", "persona": "Conversational",        "description": "Youthful, clear voice for narration"},
    {"voice": "Girish",  "gender": "Male",   "language": "en-IN", "persona": "Expressive, energetic", "description": "Warm voice with natural storytelling"},
    {"voice": "Hemraj",  "gender": "Male",   "language": "hi-IN", "persona": "Confident, authoritative", "description": "Confident voice for demos"},
    {"voice": "Ishaan",  "gender": "Male",   "language": "mr-IN", "persona": "Professional",          "description": "Clear voice for instructions and narration"},
    {"voice": "Jalaj",   "gender": "Male",   "language": "hi-IN", "persona": "Expressive, energetic", "description": "Expressive voice for storytelling"},
    {"voice": "Jwala",   "gender": "Female", "language": "hi-IN", "persona": "Friendly",              "description": "Friendly, approachable everyday voice"},
    {"voice": "Kaveri",  "gender": "Female", "language": "en-IN", "persona": "Professional",          "description": "Firm voice for customer support"},
    {"voice": "Kavin",   "gender": "Male",   "language": "kn-IN", "persona": "Professional",          "description": "Firm, articulate voice for presentations"},
    {"voice": "Kirra",   "gender": "Female", "language": "bn-IN", "persona": "Conversational",        "description": "Soft-spoken voice for casual conversations"},
    {"voice": "Lavanya", "gender": "Female", "language": "te-IN", "persona": "Warm, empathetic",      "description": "Soft, empathetic voice for care and support"},
    {"voice": "Lehara",  "gender": "Female", "language": "te-IN", "persona": "Warm, empathetic",      "description": "Gentle, reassuring voice for comfort and trust"},
    {"voice": "Mehuli",  "gender": "Female", "language": "pa-IN", "persona": "Expressive, energetic", "description": "Expressive voice for commercials and promotions"},
    {"voice": "Nalini",  "gender": "Female", "language": "hi-IN", "persona": "Friendly",              "description": "Friendly voice for playful conversations"},
    {"voice": "Noopur",  "gender": "Female", "language": "ta-IN", "persona": "Friendly",              "description": "Warm voice for everyday conversations"},
    {"voice": "Omkar",   "gender": "Male",   "language": "hi-IN", "persona": "Confident, authoritative", "description": "Energetic voice for customer support"},
    {"voice": "Poorvi",  "gender": "Female", "language": "hi-en", "persona": "Conversational",        "description": "Natural voice for bilingual conversations"},
    {"voice": "Pranav",  "gender": "Male",   "language": "en-IN", "persona": "Friendly",              "description": "Friendly voice for customer support"},
    {"voice": "Reshma",  "gender": "Female", "language": "ml-IN", "persona": "Friendly",              "description": "Bright voice for greetings and support"},
    {"voice": "Riyaan",  "gender": "Male",   "language": "ml-IN", "persona": "Conversational",        "description": "Easygoing voice for casual conversations"},
    {"voice": "Roopesh", "gender": "Male",   "language": "hi-IN", "persona": "Professional",          "description": "Grounded, knowledgeable, professional voice"},
    {"voice": "Saanvi",  "gender": "Female", "language": "kn-IN", "persona": "Expressive, energetic", "description": "Lively voice for ads and promotions"},
    {"voice": "Shlok",   "gender": "Male",   "language": "en-IN", "persona": "Conversational",        "description": "Warm, conversational voice"},
    {"voice": "Suhana",  "gender": "Female", "language": "te-IN", "persona": "Warm, empathetic",      "description": "Calm, soothing voice with confidence"},
    {"voice": "Trisha",  "gender": "Female", "language": "ta-IN", "persona": "Friendly",              "description": "Warm, approachable voice for guidance"},
    {"voice": "Trupti",  "gender": "Female", "language": "en-IN", "persona": "Professional",          "description": "Upbeat, articulate voice with maturity"},
    {"voice": "Urmila",  "gender": "Female", "language": "hi-IN", "persona": "Professional",          "description": "Refined voice for formal announcements"},
    {"voice": "Varuni",  "gender": "Female", "language": "te-IN", "persona": "Conversational",        "description": "Clear, natural voice for everyday use"},
    {"voice": "Vedika",  "gender": "Female", "language": "ta-IN", "persona": "Professional",          "description": "Crisp, articulate voice for information"},
    {"voice": "Veera",   "gender": "Male",   "language": "gu-IN", "persona": "Friendly",              "description": "Friendly voice for casual conversations"},
    {"voice": "Vikrant", "gender": "Male",   "language": "hi-IN", "persona": "Conversational",        "description": "Warm, genuine conversational voice"},
    {"voice": "Yashvi",  "gender": "Female", "language": "hi-IN", "persona": "Warm, empathetic",      "description": "Gentle, reassuring voice for comfort"},
    {"voice": "Yukti",   "gender": "Female", "language": "te-IN", "persona": "Friendly",              "description": "Warm, welcoming voice that puts listeners at ease"},
    {"voice": "Zahira",  "gender": "Female", "language": "mr-IN", "persona": "Expressive, energetic", "description": "Energetic voice for sales and casual chat"},
    {"voice": "Zayan",   "gender": "Male",   "language": "pa-IN", "persona": "Warm, empathetic",      "description": "Soft, caring voice for empathetic conversations"},
]

# ---------------------------------------------------------------------------
# Timbre v3.0 — 13 voices, each speaks all 10 languages, supports audio tags
# ---------------------------------------------------------------------------

V3_LANGUAGES = "hi-IN, en-IN, ta-IN, te-IN, kn-IN, ml-IN, mr-IN, pa-IN, bn-IN, gu-IN"

VOICE_CATALOG_V3: list[dict[str, str]] = [
    {"voice": "Avinash",  "gender": "Male",   "language": "all", "persona": "Professional",          "description": "Professional, firm voice with deliberate pacing for collections and BFSI"},
    {"voice": "Chetana",  "gender": "Female", "language": "all", "persona": "Warm, empathetic",      "description": "Gentle, empathetic voice for healthcare and telecom customer service"},
    {"voice": "Devansh",  "gender": "Male",   "language": "all", "persona": "Conversational",        "description": "Energetic, young conversational voice for sales and fintech"},
    {"voice": "Harshad",  "gender": "Male",   "language": "all", "persona": "Professional",          "description": "Professional, firm voice for collections and payment recovery"},
    {"voice": "Kalpana",  "gender": "Female", "language": "all", "persona": "Warm, empathetic",      "description": "Empathetic, composed voice for customer care and insurance"},
    {"voice": "Lakshmi",  "gender": "Female", "language": "all", "persona": "Expressive, energetic", "description": "Expressive, warm voice for storytelling and e-learning narration"},
    {"voice": "Prakash",  "gender": "Male",   "language": "all", "persona": "Professional",          "description": "Steady, deliberate voice for payment recovery and BFSI"},
    {"voice": "Riyaa",    "gender": "Female", "language": "all", "persona": "Confident, authoritative", "description": "Confident, lively voice for outbound sales and insurance"},
    {"voice": "Shivani",  "gender": "Female", "language": "all", "persona": "Warm, empathetic",      "description": "Warm, patient, empathy-first voice for inbound customer support"},
    {"voice": "Shubham",  "gender": "Male",   "language": "all", "persona": "Expressive, energetic", "description": "Energetic, confident voice for outbound sales and lead qualification"},
    {"voice": "Tarika",   "gender": "Female", "language": "all", "persona": "Warm, empathetic",      "description": "Warm, reassuring voice for banking and insurance customer care"},
    {"voice": "Vasudha",  "gender": "Female", "language": "all", "persona": "Expressive, energetic", "description": "Expressive, composed voice for narration and e-learning"},
    {"voice": "Yashraj",  "gender": "Male",   "language": "all", "persona": "Warm, empathetic",      "description": "Warm narrative voice for e-learning and IVR narration"},
]

_CATALOGS: dict[str, list[dict[str, str]]] = {
    "timbre-v2.5": VOICE_CATALOG_V25,
    "timbre-v3.0": VOICE_CATALOG_V3,
}


def get_catalog(model: str) -> list[dict[str, str]]:
    """Return the voice catalog for *model*."""
    try:
        return _CATALOGS[model]
    except KeyError:
        raise ValueError(
            f"Unknown TTS model {model!r}. Supported: {', '.join(_CATALOGS)}."
        ) from None


def resolve_voice(model: str, voice: str) -> str:
    """Return the canonical spelling of *voice* for *model*.

    Matching is case-insensitive. Raises ``ValueError`` listing the valid voices
    when the voice does not belong to the model's catalog (the API would answer
    with ``400 Bad Request``).
    """
    catalog = get_catalog(model)
    by_lower = {v["voice"].lower(): v["voice"] for v in catalog}
    canonical = by_lower.get(voice.strip().lower())
    if canonical is None:
        other = [m for m, c in _CATALOGS.items() if m != model and any(v["voice"].lower() == voice.strip().lower() for v in c)]
        hint = f" It belongs to {other[0]!r} — set model accordingly." if other else ""
        raise ValueError(
            f"Voice {voice!r} is not available for {model}.{hint} "
            f"Valid voices: {', '.join(sorted(by_lower.values()))}."
        )
    return canonical


# ---------------------------------------------------------------------------
# Audio tags (Timbre v3.0 only)
# ---------------------------------------------------------------------------

AUDIO_TAGS: tuple[str, ...] = (
    "laugh", "giggle",                                              # laughter
    "sigh", "exhales", "sniffles", "yawns", "coughs", "clears throat",  # breath
    "whispers", "shouting", "excited",                              # vocal
    "slow",                                                         # pacing
    "pauses",                                                       # silence (not spoken)
)

_TAG_RE = re.compile(r"<([A-Za-z][A-Za-z _-]*)>")


def inspect_audio_tags(text: str) -> tuple[list[str], list[str]]:
    """Return ``(known, unknown)`` tag names found in *text* (in order, de-duplicated)."""
    known: list[str] = []
    unknown: list[str] = []
    for name in _TAG_RE.findall(text):
        bucket = known if name in AUDIO_TAGS else unknown
        if name not in bucket:
            bucket.append(name)
    return known, unknown
