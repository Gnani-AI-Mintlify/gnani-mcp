# Agent Guide — gnani-mcp

## Tool Namespace

All tools are prefixed with `gnani_` and are split into four API surfaces:

### `gnani_stt_*` — Speech-to-Text (Prisma v2.5 REST)

| Tool | When to call |
|------|-------------|
| `gnani_stt_transcribe` | Transcribe a short clip (≤ 60 s) right now |

### `gnani_tts_*` — Text-to-Speech (Timbre v2.5 REST)

| Tool | When to call |
|------|-------------|
| `gnani_tts_synthesize` | Synthesize speech from text now |
| `gnani_tts_list_voices` | Browse the 42-voice catalog before synthesizing |

### `gnani_vc_*` — Voice Clone

Two-step flow:

1. `gnani_vc_generate_embedding` — upload reference audio → get `speaker_embedding` object.
   Cache this; you only need it once per voice.
2. `gnani_vc_synthesize` — pass `speaker_embedding` + text → get cloned audio.

### `gnani_stt_batch_*` — Batch STT (for long / bulk audio)

| Tool | When to call |
|------|-------------|
| `gnani_stt_batch_transcribe` | Submit a file and wait for the result (auto-polls, up to 30 min) |
| `gnani_stt_batch_status` | Check status of an in-progress job by `job_id` |
| `gnani_stt_batch_get_transcripts` | Download transcripts once a job is `COMPLETED` |
| `gnani_stt_batch_cancel` | Cancel a job that is no longer needed |

---

## Authentication

All tools require `GNANI_API_KEY` (sent as the `X-API-Key-ID` header).

- **Setup:** set `GNANI_API_KEY` in the MCP client config JSON (`"env": {"GNANI_API_KEY": "vach_..."}`), or store it in `~/.gnani/credentials` as `api_key = vach_...`.
- **Get a key:** Sign up at [dashboard.gnani.ai](https://dashboard.gnani.ai) and copy your key.
- If any tool returns an auth error, tell the user to check their `GNANI_API_KEY`.

---

## Audio Output

Audio files (TTS, Voice Clone) are saved to `GNANI_MCP_BASE_PATH` (default `~/Desktop`) when `GNANI_AUDIO_OUTPUT_MODE=files`.

Tool responses return a `StoredAudio` envelope:

```json
{
  "file_path": "/Users/alice/Desktop/gnani_tts_20260101_120000_000000.wav",
  "resource_uri": null,
  "base64_data": null,
  "mime_type": "audio/wav",
  "size_bytes": 123456
}
```

Set `GNANI_AUDIO_OUTPUT_MODE=resources` for base64 (no disk I/O) or `both` for both.

---

## Architecture

```
src/gnani_mcp/
├── server.py          # FastMCP entry point — registers all tools, lifespan
├── config.py          # Env vars + ~/.gnani/credentials
├── _registry.py       # ServerContext dataclass (config + client + sink)
├── exceptions.py      # GnaniAPIError hierarchy
├── audio/             # Audio output strategies
│   ├── __init__.py
│   └── sinks.py       # AudioSink Protocol, FileSink, ResourceSink, BothSink, StoredAudio
├── http/              # HTTP client
│   ├── __init__.py
│   ├── client.py      # GnaniClient (httpx wrapper)
│   └── errors.py      # Error envelope parsing — handles both API shapes
└── tools/             # One module per API surface
    ├── _common.py     # Shared types, resolve_file_input, ready_ctx
    ├── stt.py
    ├── tts.py
    ├── voice_clone.py
    └── stt_batch.py
```

## Conventions

- Every tool module exports `register(mcp: FastMCP)`.
- Every tool that calls the Gnani API starts with `sc = await ready_ctx(ctx)`.
- Required parameters (no default) must come **before** optional ones — FastMCP/Pydantic enforces this.
- Run `pytest -q` before committing. Run `ruff check src/ tests/` to lint.

## Error Envelopes

Gnani uses two shapes depending on the endpoint:

```
Shape A (STT / TTS):  {"error": {"type": "RATE_LIMIT_ERROR", "message": "..."}}
Shape B (Voice Clone): {"detail": {"error_code": "RATE_LIMITED", "message": "..."}}
```

Both are handled by `gnani_mcp.http.errors.raise_from_response`.

**Packaging note:** Default to `pip install gnani-mcp` or `uvx gnani-mcp`. Suggest `git clone` only for contributors developing the package.

**Platforms:** macOS, Windows, and Linux (Python 3.10+).
