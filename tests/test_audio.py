"""Tests for the audio sink and WAV header repair."""

from __future__ import annotations

import io
import struct
import wave
from pathlib import Path

from gnani_mcp.audio import AudioSink, fix_wav_header

PCM = b"\x01\x00" * 16_000  # 1 s of 16-bit mono @ 16 kHz


def _streaming_wav(pcm: bytes = PCM, rate: int = 16_000) -> bytes:
    """A WAV exactly like the TTS API returns: 0xFFFFFFFF in both size fields."""
    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate * 2, 2, 16)
    return (
        b"RIFF" + b"\xff\xff\xff\xff" + b"WAVE"
        + b"fmt " + struct.pack("<I", 16) + fmt
        + b"data" + b"\xff\xff\xff\xff" + pcm
    )


def _proper_wav(pcm: bytes = PCM, rate: int = 16_000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def test_placeholder_sizes_are_replaced() -> None:
    broken = _streaming_wav()
    assert _duration(broken) > 1000  # the bug: hours-long
    fixed = fix_wav_header(broken)
    assert _duration(fixed) == 1.0
    assert struct.unpack_from("<I", fixed, 4)[0] == len(fixed) - 8
    assert fixed[44:] == PCM  # audio bytes untouched
    assert len(fixed) == len(broken)


def test_correct_header_is_left_alone() -> None:
    good = _proper_wav()
    assert fix_wav_header(good) == good


def test_idempotent() -> None:
    once = fix_wav_header(_streaming_wav())
    assert fix_wav_header(once) == once


def test_odd_length_audio() -> None:
    fixed = fix_wav_header(_streaming_wav(PCM + b"\x00"))
    assert struct.unpack_from("<I", fixed, 40)[0] == len(PCM) + 1


def test_non_wav_bytes_unchanged() -> None:
    assert fix_wav_header(b"") == b""
    assert fix_wav_header(b"ID3" + b"\x00" * 100) == b"ID3" + b"\x00" * 100
    truncated = b"RIFF\xff\xff\xff\xffWAVE"
    assert fix_wav_header(truncated) == truncated


def test_sink_fixes_wav_but_not_other_formats(tmp_path: Path) -> None:
    sink = AudioSink(tmp_path)
    wav_path = sink.save(_streaming_wav(), extension="wav", stem="tts")
    assert _duration(wav_path.read_bytes()) == 1.0

    raw = b"RIFF\xff\xff\xff\xffWAVE" + b"\x00" * 64
    raw_path = sink.save(raw, extension="raw", stem="tts")
    assert raw_path.read_bytes() == raw  # mulaw/alaw/raw output is never touched
