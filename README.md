# gnani-mcp

Official Gnani AI MCP server. Exposes Gnani Speech-to-Text (Prisma v2.5), Text-to-Speech (Timbre v2.5), Voice Clone, and Batch STT APIs as first-class MCP tools, so any MCP-aware client (Claude Desktop, Claude Code, Cursor, Windsurf, Zed) can call them with zero boilerplate.

Cross-platform Python package: **macOS, Windows, and Linux** (Python 3.10+).

---

## Quickstart

### 1. Get your API key

Sign up or log in at **dashboard.gnani.ai** and copy your API key.

### 2. Add to your MCP client

Paste this into your MCP config JSON:

```json
{
  "mcpServers": {
    "gnani": {
      "command": "uvx",
      "args": ["gnani-mcp"],
      "env": {
        "GNANI_API_KEY": "your-api-key"
      }
    }
  }
}
```

Replace `your-api-key` with your actual API key.

If you have installed via `pip install gnani-mcp`, use the console script directly:

```json
{
  "mcpServers": {
    "gnani": {
      "command": "gnani-mcp",
      "env": {
        "GNANI_API_KEY": "your-api-key"
      }
    }
  }
}
```

### 3. Config file locations

| Client | Config path |
|--------|-------------|
| **Cursor** | `~/.cursor/mcp.json` (macOS/Linux) · `%USERPROFILE%\.cursor\mcp.json` (Windows) |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) |
| **Claude Code** | `claude mcp add gnani -- uvx gnani-mcp` (then set `GNANI_API_KEY` env var) |
| **Windsurf** | Cascade settings → MCP servers |
| **Zed** | `settings.json` → `context_servers` |

### Alternative: credentials file

Instead of setting `GNANI_API_KEY` in the JSON config, you can store it in `~/.gnani/credentials`:

```ini
api_key = your-api-key
```

The server checks `GNANI_API_KEY` env var first, then falls back to `~/.gnani/credentials`.

---

## Install

```bash
# Option A: run directly (no install needed)
uvx gnani-mcp

# Option B: install globally
pip install gnani-mcp
```

---

## Tools

| Tool | What it does |
|------|-------------|
| `gnani_stt_transcribe` | Transcribe audio (≤ 60 s) in 10 Indian languages — WAV, MP3, OGG, FLAC, AAC, M4A |
| `gnani_tts_synthesize` | Synthesize speech from text — 42 voices, 10 languages + Hinglish |
| `gnani_tts_list_voices` | Browse the full voice catalog with language, gender, persona, description |
| `gnani_vc_generate_embedding` | Extract a speaker embedding from a reference audio clip (step 1 of voice cloning) |
| `gnani_vc_synthesize` | Synthesize speech in a cloned voice using a speaker embedding (step 2) |
| `gnani_stt_batch_transcribe` | Submit an audio file for batch transcription and poll until complete |
| `gnani_stt_batch_status` | Poll the status of a running batch job by job ID |
| `gnani_stt_batch_get_transcripts` | Download transcripts for a completed batch job |
| `gnani_stt_batch_cancel` | Cancel a running batch job |

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `GNANI_API_KEY` | — | **Required.** Your Gnani API key. |
| `GNANI_API_BASE_URL` | `https://api.vachana.ai` | Override for testing / staging. |
| `GNANI_MCP_BASE_PATH` | `~/Desktop` | Directory where audio output files are saved. |
| `GNANI_AUDIO_OUTPUT_MODE` | `files` | `files` · `resources` (base64, no disk) · `both` |

---

## Supported Languages

### STT (Prisma v2.5)

| Language | Code |
|----------|------|
| Bengali | `bn-IN` |
| English (India) | `en-IN` |
| Gujarati | `gu-IN` |
| Hindi | `hi-IN` |
| Kannada | `kn-IN` |
| Malayalam | `ml-IN` |
| Marathi | `mr-IN` |
| Punjabi | `pa-IN` |
| Tamil | `ta-IN` |
| Telugu | `te-IN` |

### TTS (Timbre v2.5) — also supports Hinglish (`hi-en`) and `auto`

42 voices across all 10 Indian languages plus Hinglish. Use `gnani_tts_list_voices` to browse by language and gender.

---

## Voice Clone Workflow

```python
# Step 1 — generate embedding from reference audio (do this once per voice)
embedding_result = gnani_vc_generate_embedding(audio_path="/path/to/reference.wav")
speaker_embedding = embedding_result["speaker_embedding"]

# Step 2 — synthesize with the cloned voice (reuse embedding as many times as needed)
audio_result = gnani_vc_synthesize(
    text="नमस्ते, आप कैसे हैं?",
    speaker_embedding=speaker_embedding,
)
print(audio_result["file_path"])  # absolute path to the saved WAV file
```

---

## HTTP Transport

By default `gnani-mcp` runs over stdio (the standard MCP transport for local clients).  
To expose the server over HTTP instead:

```bash
gnani-mcp --transport http --host 127.0.0.1 --port 8000 --path /mcp
```

Then point your client at `http://127.0.0.1:8000/mcp`.  
Use `--transport sse` or `--transport streamable-http` for SSE-based transports.

---

## Development

```bash
# Clone and set up
git clone https://github.com/gnani-ai/gnani-mcp.git
cd gnani-mcp

uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests
pytest -q

# Lint / format
ruff check src/ tests/
ruff format src/ tests/

# Run the MCP server locally (stdio)
gnani-mcp

# Run over HTTP
gnani-mcp --transport http --port 8000

# Print MCP client config JSON
gnani-mcp --print
gnani-mcp --api-key=your-key --print
```

### Releasing to PyPI

1. Bump `version` in `pyproject.toml`.
2. Push a tag of the form `vX.Y.Z-qa`:

   ```bash
   git tag v0.1.1-qa && git push origin v0.1.1-qa
   ```

3. The **Publish to PyPI** GitHub Actions workflow runs automatically, verifies the tag matches the version, builds, and uploads to PyPI via [OIDC Trusted Publisher](https://docs.pypi.org/trusted-publishers/) (no API key required).

---

## License

[MIT](LICENSE)
