# gnani-mcp

Official Gnani AI MCP server. Exposes Gnani Speech-to-Text (Prisma v2.5 / v3.0), Text-to-Speech (Timbre v2.5 / v3.0), and Voice Clone APIs as first-class MCP tools, so any MCP-aware client (Claude Desktop, Claude Code, Cursor, Windsurf, Zed) can call them with zero boilerplate.

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
| `gnani_stt_transcribe` | Transcribe a short clip (≤ 30 s) in 10 Indian languages — WAV, MP3, OGG, FLAC, AAC, M4A. `model`: `prisma-v2.5` (default) or `prisma-v3.0` |
| `gnani_stt_batch_transcribe` | Transcribe long (up to 4 h) or remote audio: create → start → poll → fetch, in one call. Supports both models |
| `gnani_stt_batch_list_jobs` | List Batch STT jobs (status filter + cursor pagination) |
| `gnani_stt_batch_status` / `_get_transcripts` / `_cancel` | Check, download, or cancel an existing Batch job |
| `gnani_tts_synthesize` | Synthesize speech. `model`: `timbre-v2.5` (default, 42 voices) or `timbre-v3.0` (13 voices, all 10 languages, inline audio tags) |
| `gnani_tts_list_voices` | Browse the voice catalog for either TTS model (language, gender, persona, description) |
| `gnani_vc_generate_embedding` | Extract a speaker embedding from a reference audio clip (step 1 of voice cloning) |
| `gnani_vc_synthesize` | Synthesize speech in a cloned voice using a speaker embedding (step 2) |

### Choosing a model

Both new models are **opt-in** — omit `model` and behaviour is unchanged (Prisma v2.5 / Timbre v2.5).

**Prisma v3.0** (`model="prisma-v3.0"`) on `gnani_stt_transcribe` and `gnani_stt_batch_transcribe`:

- `language_code="indic-auto"` lets the model identify the language, or pass 1–4 comma-separated codes (`"hi-IN,en-IN"`) as hints. REST results include `detected_language_code`.
- `format` adds `codemix` (English words stay Latin) and, on REST only, `transliterate` (Latin-letter output). When `format` is omitted v3.0 picks a style per request (digits for a single `hi-IN`/`en-IN`) — pass `format` explicitly to keep v2.5-style output.
- Context hints: `keyterms`, `topic`, `speaker_names`, and (REST only) `previous_text`. On Batch only one of `keyterms`, `topic`, `topic + keyterms`, or `speaker_names` is accepted, and `topic` must be 30–1,600 characters.

**Timbre v3.0** (`model="timbre-v3.0"`) on `gnani_tts_synthesize`:

- Voices are **not** shared between models: Shivani, Lakshmi, Kalpana, Chetana, Vasudha, Riyaa, Tarika (F); Avinash, Shubham, Prakash, Devansh, Yashraj, Harshad (M). Every voice speaks all 10 languages.
- Inline audio tags in `text`: `<laugh>`, `<giggle>`, `<sigh>`, `<exhales>`, `<sniffles>`, `<yawns>`, `<coughs>`, `<clears throat>`, `<whispers>`, `<shouting>`, `<excited>`, `<slow>`, `<pauses>` (silence, never spoken). A tag applies until the next tag; tags are billed as characters. With v2.5 they are stripped, and the tool returns a warning.

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `GNANI_API_KEY` | — | **Required.** Your Gnani API key. |
| `GNANI_API_BASE_URL` | `https://api.vachana.ai` | Override for testing / staging. |
| `GNANI_MCP_BASE_PATH` | `~/Desktop` | Directory where audio output files are saved. |
| `GNANI_AUDIO_OUTPUT_MODE` | `files` | `files` · `resources` · `both` |

---

## Supported Languages

### STT (Prisma v2.5 / v3.0)

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

### TTS (Timbre v2.5 / v3.0) — also supports Hinglish (`hi-en`) and `auto`

Timbre v2.5: 42 voices across all 10 Indian languages plus Hinglish, one preferred language each. Timbre v3.0: 13 voices that each speak all 10 languages. Use `gnani_tts_list_voices` (with `model`) to browse.

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
print(audio_result["audio_file"])  # path to saved WAV file
```

---

## Development

```bash
# Clone and set up
git clone https://github.com/Gnani-AI-Mintlify/gnani-mcp.git
cd gnani-mcp

uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run tests
pytest -q

# Run the MCP server locally
gnani-mcp

# Print client config JSON
gnani-mcp --print
gnani-mcp --api-key=your-key --print
```

---

## License

[MIT](LICENSE)
