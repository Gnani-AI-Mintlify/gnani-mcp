# gnani-mcp

Official Gnani AI MCP server. Exposes Gnani Speech-to-Text (Prisma v2.5 / v3.0) and Text-to-Speech (Timbre v2.5 / v3.0) APIs as first-class MCP tools, so any MCP-aware client (Cursor, Claude Code, Claude Desktop, Codex, Windsurf, Zed) can call them with zero boilerplate.

Cross-platform Python package: **macOS, Windows, and Linux** (Python 3.10+).

You never call the tools yourself. You ask your agent in plain English (*"Transcribe `/Users/me/call.wav` in Hindi"*), and it picks the tool and fills in the inputs. The server runs **on your own computer**: it reads audio files from your disk, sends them to the Gnani API with your API key, and saves generated audio back to your disk.

---

## Contents

- [Quickstart](#quickstart)
- [Setting your API key](#setting-your-api-key)
- [Install](#install)
- [Connect your agent](#connect-your-agent)
- [Example prompts](#example-prompts)
- [Tools](#tools)
- [Languages and voices](#languages-and-voices)
- [Configuration](#configuration)
- [Running over HTTP](#running-over-http)
- [Troubleshooting](#troubleshooting)
- [Security and costs](#security-and-costs)

---

## Quickstart

### 1. Get your API key

Sign up or log in at **app.gnani.ai** and copy your API key. Treat it like a password.

### 2. Add to your MCP client

You need [`uv`](https://docs.astral.sh/uv/) (`brew install uv`, or `curl -LsSf https://astral.sh/uv/install.sh | sh`; Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`). Open a new terminal afterwards. Then paste this into your MCP config JSON:

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

Replace `your-api-key` with your actual API key, then restart the agent.

If you have installed via `pip install gnani-mcp`, use the console script directly (use its full path if your agent can't find it):

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

### 3. Check that it works

Ask your agent: *"List my recent Gnani batch transcription jobs."* This asks the Gnani API for your jobs and processes no audio.

| What you get | What it means |
|---|---|
| A list of jobs (maybe empty) | The server found your key and the API accepted it. You're set. |
| `GNANI_API_KEY is not set. ...` | The server didn't find a key. See [Setting your API key](#setting-your-api-key), then restart the agent. |
| `[HTTP 401 INVALID_API_KEY] Unauthorized` | A key was found but rejected. Re-copy it from app.gnani.ai and check both places it can be set. |

Don't use *"list the voices"* as the test: that reads a built-in catalog and works with no key at all.

---

## Setting your API key

Your agent starts the server as a **separate background program**, and a program only knows what it is handed when it starts. It does not see what you typed in a terminal earlier, so the key has to be placed where the server looks **at the moment it starts**.

The server looks here, in this order (the first one found wins):

| Order | Place | Typical use |
|---|---|---|
| 1 | The `GNANI_API_KEY` **environment variable** of the server process | The `env` block in your agent's config |
| 2 | The file `~/.gnani/credentials` | One-time setup that works with every agent and keeps the key out of config files |

If neither is found, the server still starts, but every tool call that needs the API fails with a message saying the key is missing.

**Method A: the agent's config (simplest).** Put it in the `env` block, as in the Quickstart. Restart the agent afterwards (for Claude Desktop, quit it fully).

**Method B: the credentials file.** Create it once and every agent picks it up, with no `env` block needed.

```bash
mkdir -p ~/.gnani
printf 'api_key = YOUR_GNANI_API_KEY\n' > ~/.gnani/credentials
chmod 600 ~/.gnani/credentials
```

On Windows (PowerShell):

```powershell
New-Item -ItemType Directory -Force "$HOME\.gnani" | Out-Null
Set-Content "$HOME\.gnani\credentials" 'api_key = YOUR_GNANI_API_KEY'
```

The line must be `api_key = your-key`, with the name in lowercase. Writing `GNANI_API_KEY=...` in this file is silently ignored. Quotes around the key are allowed; don't add `export`. Blank lines and lines starting with `#` are ignored.

**Method C: `export GNANI_API_KEY=...` in a terminal.** Only for running the server by hand. Desktop apps (Cursor, Claude Desktop) are usually launched from the Dock or Start menu, so they never see it. Use A or B for agents.

### Common mistakes

| What happened | Fix |
|---|---|
| `gnani-mcp --api-key=MYKEY` still says the key is missing | `--api-key` only works with `--print`, to write the key into the config snippet it prints. It doesn't set the key for a running server. Use A, B or C. |
| I put `GNANI_API_KEY=...` in `~/.gnani/credentials` and nothing happened | The file wants `api_key = ...`. |
| I ran `export GNANI_API_KEY=...` but my desktop agent can't see it | The app wasn't started from that terminal. Use the `env` block or the credentials file. |
| I edited the config but nothing changed | The server was already running. Restart the agent or reload its MCP servers. |
| I still get `401` | Typo, extra spaces or line breaks, the placeholder (`your-api-key`) is still there, or an older key in the config overrides the file. Re-copy the key and check both places. |

When you start the server yourself, it prints a line like `gnani-mcp ready · v0.2.2 · ... · auth=configured`. `auth=configured` means *a* key was found (not that it's valid); `auth=missing` means none was. Agents with logs (for example Cursor's **MCP Logs**) show the same line.

---

## Install

```bash
# Option A: run directly (no install needed)
uvx gnani-mcp

# Option B: install globally
pip install gnani-mcp
```

With `pip`, use a virtual environment (`python3 -m venv ~/.gnani-mcp-venv && ~/.gnani-mcp-venv/bin/pip install gnani-mcp`) and put the full path to `~/.gnani-mcp-venv/bin/gnani-mcp` as the `command` in your config (Windows: `%USERPROFILE%\.gnani-mcp-venv\Scripts\gnani-mcp.exe`). `gnani-mcp --help` checks the install; it doesn't check your key.

`gnani-mcp --print` (or `uvx gnani-mcp --print`, or `gnani-mcp --api-key=your-key --print`) prints a ready-made client config for your machine.

---

## Connect your agent

Every agent needs the same three values: command `uvx` (or the full path to `gnani-mcp`), arguments `gnani-mcp`, and the `GNANI_API_KEY` environment (optional if you use the credentials file).

| Client | Where / how |
|--------|-------------|
| **Cursor** | `~/.cursor/mcp.json` (Windows: `%USERPROFILE%\.cursor\mcp.json`), or `.cursor/mcp.json` in a project. Same `mcpServers` JSON as above. To keep the key out of the file use `"GNANI_API_KEY": "${env:GNANI_API_KEY}"`, or rely on the credentials file. Check Settings → MCP: `gnani` should show 8 tools. |
| **Claude Code** | `claude mcp add gnani --env GNANI_API_KEY=your-api-key -- uvx gnani-mcp`, then `claude mcp list` (should show `✔ Connected`). For a shared project, put the `mcpServers` JSON in `.mcp.json` **without** the key and use the credentials file. |
| **Claude Desktop** | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) · `%APPDATA%\Claude\claude_desktop_config.json` (Windows), or Settings → Developer → Edit Config. Quit and reopen the app fully. If you see `spawn uvx ENOENT`, use the full path from `which uvx` (Windows: `where uvx`) as the `command`. |
| **Codex** | `codex mcp add gnani --env GNANI_API_KEY=your-api-key -- uvx gnani-mcp`, or edit `~/.codex/config.toml` (below). Check with `/mcp`. |
| **Windsurf** | Cascade panel → MCPs → *Open MCP config file* (`~/.config/devin/mcp_config.json` on macOS/Linux, `%APPDATA%\devin\mcp_config.json` on Windows; older installs use `~/.codeium/windsurf/mcp_config.json`). Same `mcpServers` JSON as above. |
| **Zed** | `settings.json` (`zed: open settings file`) → `context_servers`, see below. Or Settings → AI → MCP Servers → *Add Server*. |

**Codex** gives a server 10 seconds to start and a tool call 60 seconds by default. The first `uvx` run downloads the package and batch transcription takes minutes, so raise both:

```toml
[mcp_servers.gnani]
command = "uvx"
args = ["gnani-mcp"]
startup_timeout_sec = 60
tool_timeout_sec = 1800

[mcp_servers.gnani.env]
GNANI_API_KEY = "your-api-key"
```

**Zed** uses a different key (`context_servers`) than the JSON above:

```json
{
  "context_servers": {
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

Cursor has been tested with this server. Other clients follow each vendor's MCP documentation; any client that supports MCP stdio servers should work.

---

## Example prompts

Just ask in plain English; you don't need to name tools. Always give **full file paths** (`/Users/me/audio/call.wav`).

**Transcribe**
- *"Transcribe `/Users/me/audio/customer-call.wav`. It's in Hindi."*
- *"Transcribe this clip and detect the language automatically: `/Users/me/clip.mp3`. Use the newest model."*
- *"Transcribe `/Users/me/sales-call.wav` in Hindi, and make sure these words are spelled right: Gnani, Vachana, Prisma."*
- *"Transcribe this recording keeping English words in English letters: `/Users/me/meeting.m4a`. Hindi mixed with English."*

**Long audio**
- *"This is a 2-hour call: `/Users/me/long-call.mp3`. Transcribe it in Tamil and tell me who said what."*
- *"Transcribe https://example.com/call-42.wav in English and separate the speakers."*
- *"Show me my recent batch jobs, then give me the transcript of the last completed one."*

**Generate speech**
- *"Read this out in a Hindi female voice and save it as an MP3: 'नमस्ते, गनानी में आपका स्वागत है।'"*
- *"What voices are available for Telugu?"*
- *"Say this with a laugh in the middle, using a female voice on the newest model: 'Let me check… `<laugh>` found it!'"*
- *"Make an 8 kHz telephone-quality version of this announcement for an IVR."*

**Combine**
- *"Transcribe `/Users/me/call.wav` in Hindi, summarize it in three bullets, then read the summary back in a female English voice."*

Tips: name the language; clips up to 30 seconds go through short transcription, longer audio through the batch tool (which checks every 10 seconds, so be patient); for text-to-speech pick a voice first (*"What voices do you have for Hindi?"*).

---

## Tools

The server provides **8 tools**. Generated audio is saved to a file and the response includes its path.

| Tool | What it does |
|------|-------------|
| `gnani_stt_transcribe` | Transcribe a short clip (≤ 30 s) in 10 Indian languages — WAV, MP3, OGG, FLAC, AAC, M4A. `model`: `prisma-v2.5` (default) or `prisma-v3.0` |
| `gnani_stt_batch_transcribe` | Transcribe long (up to 4 h) or remote audio: create → start → poll → fetch, in one call. Supports both models |
| `gnani_stt_batch_list_jobs` | List Batch STT jobs (status filter + cursor pagination) |
| `gnani_stt_batch_status` / `_get_transcripts` / `_cancel` | Check, download, or cancel an existing Batch job |
| `gnani_tts_synthesize` | Synthesize speech. `model`: `timbre-v2.5` (default, 42 voices) or `timbre-v3.0` (34 voices, all 10 languages, inline audio tags) |
| `gnani_tts_list_voices` | Browse the voice catalog for either TTS model (language, gender, persona, description) |

### Choosing a model

Both new models are **opt-in**: omit `model` and behaviour is unchanged (Prisma v2.5 / Timbre v2.5).

**Prisma v3.0** (`model="prisma-v3.0"`) on `gnani_stt_transcribe` and `gnani_stt_batch_transcribe`:

- `language_code="indic-auto"` lets the model identify the language, or pass 1–4 comma-separated codes (`"hi-IN,en-IN"`) as hints. REST results include `detected_language_code`.
- `format` adds `codemix` (English words stay Latin) and, on REST only, `transliterate` (Latin-letter output). When `format` is omitted v3.0 picks a style per request (digits for a single `hi-IN`/`en-IN`) — pass `format` explicitly to keep v2.5-style output.
- Context hints: `keyterms`, `topic`, `speaker_names`, and (REST only) `previous_text`. On Batch only one of `keyterms`, `topic`, `topic + keyterms`, or `speaker_names` is accepted, and `topic` must be 30–1,600 characters.

Output styles: **verbatim** spells numbers as words and writes English words in the native script; **transcribe** uses written forms (₹5,000); **codemix** keeps English words in English letters; **transliterate** gives the whole transcript in Latin letters. v2.5 defaults to `verbatim`; v3.0 uses `transcribe` for a single `hi-IN` or `en-IN` and `verbatim` otherwise.

**Timbre v3.0** (`model="timbre-v3.0"`) on `gnani_tts_synthesize`:

- Voices are **not** shared between models. There are 34 Timbre v3.0 voices, and every voice speaks all 10 languages. Female: Anitasingh, Chetana, Kalpana, Lakshmi, Lakshmidevi, Neelam, Priyasharm, Rajni, Rekha, Riyaa, Shivani, Shruthi, Sneha, Sohini, Sunaina, Swathi, Tarika, Vasudha. Male: Arko, Avinash, Devansh, Harshad, Mahendra, Manjunath, Nitin, Prakash, Rahulmehta, Rajeev, Rakesh, Santosh, Shubham, Vikramdasu, Vinod, Yashraj.
- `speed` is optional. On Timbre v3.0 it accepts 0.8 to 1.2 (the service snaps it to 0.8, 1.0 or 1.2); on Timbre v2.5 it accepts 0.85 to 1.15. When you leave it out, the voice's recommended speed is used. A value outside the model's range is rejected before the API is called.
- Inline audio tags in `text`: `<laugh>`, `<giggle>`, `<sigh>`, `<exhales>`, `<sniffles>`, `<yawns>`, `<coughs>`, `<clears throat>`, `<whispers>`, `<shouting>`, `<excited>`, `<slow>`, `<pauses>` (silence, never spoken). A tag applies until the next tag; tags are billed as characters. With v2.5 they are stripped, and the tool returns a warning.

### `gnani_stt_transcribe` parameters

| Parameter | What it means |
|---|---|
| `audio_path` / `audio_base64` / `audio_url` | Exactly one of: full path to a local file, base64 audio, or a direct link. Base64 and URL need `filename` (with extension). Max 25 MB for base64/URL. |
| `language_code` | v2.5: one code such as `hi-IN`. v3.0: `indic-auto` or up to 4 codes. Optional only with v3.0 `transliterate`. |
| `model`, `format` | See above. |
| `keyterms`, `topic`, `previous_text`, `speaker_names` | v3.0 context hints (up to 200 keyterms; `topic` up to 1,600 characters; `previous_text` uses the last 600 characters; 1–4 `speaker_names`, a spelling aid, not speaker separation). |
| `itn_native_numerals` | v2.5 only, with `format="transcribe"`: digits in the native script. |
| `enable_substitution` + `substitution_map` | Find-and-replace on the final text (up to 10 rules). |

Returns `transcript`, `model`, `request_id` and (v3.0) `detected_language_code`.

### `gnani_stt_batch_transcribe` parameters

| Parameter | What it means |
|---|---|
| `language_code` | Required. v2.5: one code, or up to 3 for per-file detection. v3.0: `indic-auto` or 1–4 codes. |
| `audio_path` / `audio_url` | One of: local file (**max 10 MB** this way) or a public link (up to 4 hours). Formats: WAV, MP3, MP4, FLAC, OGG, Opus, M4A, AAC, WebM, AMR. |
| `model`, `format` | `format` is v3.0 only here (`transliterate` isn't available for batch). |
| `with_diarization`, `num_speakers` | Separate speakers; `num_speakers` (1–8) is an upper limit, not a target. |
| `with_denoise` | Clean noisy audio first. Leave off for clean recordings. |
| `is_multi_channel` | Only for true multi-channel files. |
| `keyterms`, `topic`, `speaker_names` | v3.0 only; use one of the allowed combinations (see above). |
| `callback_url` | HTTPS address Gnani posts results to when the job finishes. |

The call waits while the job runs (checks every 10 seconds, up to 30 minutes). If it is cut short, the job keeps running on Gnani's servers; use `gnani_stt_batch_list_jobs`, `_status` and `_get_transcripts` to pick it up. `_cancel` works while a job is `CREATED`, `STARTING`, `QUEUED` or `IN_PROGRESS`. Transcript links expire after an hour; call `_get_transcripts` again for fresh ones.

### `gnani_tts_synthesize` parameters

| Parameter | What it means |
|---|---|
| `text`, `voice` | Required. The voice must belong to the chosen model (not case-sensitive). A voice from the other model is rejected, and the message names the right model. |
| `model` | `timbre-v2.5` (default) or `timbre-v3.0`. |
| `language` | `auto` (default, detected from the script), or a code such as `hi-IN`, `hi-en` (Hinglish). With v2.5, match the voice's language. |
| `speed` | Optional, see above. 1.0 is normal. |
| `container` | `wav` (default), `mp3`, `ogg`, `raw`, `mulaw`, `alaw` (the last two are 8,000 Hz phone formats). |
| `sample_rate` | 8000, 16000, 22050, 24000, 44100 or 48000 Hz (default 48000). |
| `bitrate` | MP3 only: `32k` to `192k`. |

Returns `audio_file` (full path), `size_bytes`, `model`, `voice`, `language`, `container`, `sample_rate`, and `warnings` if something was adjusted. `gnani_tts_list_voices` (`model`, `language` for v2.5, `gender`) reads a catalog built into the server and makes no API call.

---

## Languages and voices

### STT (Prisma v2.5 / v3.0)

| Language | Code | | Language | Code |
|---|---|---|---|---|
| Bengali | `bn-IN` | | Malayalam | `ml-IN` |
| English (India) | `en-IN` | | Marathi | `mr-IN` |
| Gujarati | `gu-IN` | | Punjabi | `pa-IN` |
| Hindi | `hi-IN` | | Tamil | `ta-IN` |
| Kannada | `kn-IN` | | Telugu | `te-IN` |

Prisma v3.0 also accepts `indic-auto` and comma-separated hints such as `hi-IN,en-IN`.

### TTS (Timbre v2.5 / v3.0) — also supports Hinglish (`hi-en`) and `auto`

**Timbre v2.5:** 42 voices across the 10 languages plus Hinglish, one preferred language each.

| Language | Female | Male |
|---|---|---|
| Hindi (`hi-IN`) | Ambuja, Bhavna, Chitra, Jwala, Nalini, Urmila, Yashvi | Deepak, Hemraj, Jalaj, Omkar, Roopesh, Vikrant |
| English (`en-IN`) | Devika, Kaveri, Trupti | Girish, Pranav, Shlok |
| Hinglish (`hi-en`) | Poorvi | none |
| Tamil (`ta-IN`) | Asmita, Brinda, Noopur, Trisha, Vedika | none |
| Telugu (`te-IN`) | Lavanya, Lehara, Suhana, Varuni, Yukti | none |
| Kannada (`kn-IN`) | Saanvi | Kavin |
| Malayalam (`ml-IN`) | Reshma | Riyaan |
| Marathi (`mr-IN`) | Zahira | Ishaan |
| Bengali (`bn-IN`) | Kirra | Dhruva |
| Gujarati (`gu-IN`) | Falak | Veera |
| Punjabi (`pa-IN`) | Mehuli | Zayan |

**Timbre v3.0:** 34 voices that each speak all 10 languages (listed above). There are no male Tamil or Telugu voices on v2.5, so use a v3.0 voice for those. No voice name appears in both lists. Use `gnani_tts_list_voices` (with `model`) for each voice's persona and description.

---

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `GNANI_API_KEY` | — | **Required** (or use `~/.gnani/credentials`). Your Gnani API key. |
| `GNANI_MCP_BASE_PATH` | `~/Desktop` | Directory where audio output files are saved (created if missing). Files are named like `gnani_tts_20261103_175002_945517.wav`; each call writes a new file. |

Set them in the `env` block of your agent's config, for example `"GNANI_MCP_BASE_PATH": "/Users/me/projects/audio-output"`.

---

## Running over HTTP

By default the server speaks MCP over stdio: your agent starts it and talks to it through standard input and output. That's why a server you start by hand looks idle after printing its log line. Press `Ctrl+C` to stop it.

For clients that want a web address instead of a command, start the server yourself:

```bash
GNANI_API_KEY="your-api-key" gnani-mcp --transport http --host 127.0.0.1 --port 8000 --path /mcp
```

`--transport` accepts `stdio` (default), `http`, `sse`, or `streamable-http`. Point the client at `http://127.0.0.1:8000/mcp`, for example in Cursor: `{ "mcpServers": { "gnani": { "url": "http://127.0.0.1:8000/mcp" } } }`.

- **The key goes to the server, not the client.** Set it in the terminal that starts the server, or in `~/.gnani/credentials`. Putting it in the client's config does nothing.
- **There is no login on the web address.** Anyone who can reach the port can use your Gnani account through it. Keep `--host 127.0.0.1` and don't expose the port to a network.

---

## Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| The server doesn't appear in my agent | Config in the wrong place or invalid JSON (missing commas or quotes). Restart the agent (Claude Desktop: quit fully). |
| `command not found` / `spawn uvx ENOENT` | The agent can't find `uvx`. Install `uv`, open a new terminal, and use the full path from `which uvx` (Windows: `where uvx`) as the `command`. |
| Times out on first start (Codex) | First launch downloads the package. Set `startup_timeout_sec = 60`. |
| Long transcription fails with a timeout | Your agent's tool timeout is too short (batch can wait up to 30 minutes). Codex: `tool_timeout_sec = 1800`. Claude Code: set `MCP_TOOL_TIMEOUT` (milliseconds). The Gnani job keeps running: ask for its status or transcripts afterwards. |
| `401` / `INVALID_API_KEY` | The key has a typo, extra spaces or quotes, or isn't valid. Re-copy it from app.gnani.ai. |
| `403` / `SCOPE_NOT_ALLOWED` | Your key isn't allowed to use that product or model. Contact support@gnani.ai. |
| Error mentions `GNANI_API_KEY` or `~/.gnani/credentials` | No key found. See [Setting your API key](#setting-your-api-key), then restart the agent. |
| Log says `auth=missing` though I set the key | The key isn't reaching the server process. See the common mistakes under [Setting your API key](#setting-your-api-key). |
| Log says `auth=configured` but calls fail with `401` | A key was found but it's wrong: typo, leftover placeholder, or an older key in the config overriding the credentials file. |
| `Audio file not found` | The path is wrong or relative. Use the full absolute path. |
| `Unsupported audio format` | Short clips: WAV, MP3, OGG, FLAC, AAC, M4A. Batch also accepts MP4, Opus, WebM and AMR. With base64/URL input, give `filename` the right extension. |
| `Unsupported language code` | Use a code from [Languages and voices](#languages-and-voices). Prisma v2.5 accepts one language. |
| `Voice 'X' is not available for timbre-…` | Voices belong to one model. The message names the model and lists valid voices. |
| Audio tags were removed from my text | Tags only work with `timbre-v3.0`. |
| `speed ... is outside the range` | Timbre v3.0: 0.8–1.2. Timbre v2.5: 0.85–1.15. Or leave `speed` unset. |
| Can't find the generated audio | Check `audio_file` in the response. Default folder is your Desktop (`GNANI_MCP_BASE_PATH`). |
| `429` | The server retries up to 5 times. If you still see it, wait and avoid many parallel requests. |
| `504` / "did not respond within 120s" | The Gnani API took too long. Try again; for long audio use batch transcription. |
| Empty transcript | Check the clip contains speech; the minimum clip length is 0.1 seconds. |

Logs: Cursor → Output panel → **MCP Logs**; Claude Code → `claude mcp list`, `claude mcp get gnani`, `/mcp`; Codex → `/mcp`. The server writes its log lines to stderr, which most clients capture.

Still stuck? Contact support@gnani.ai with the error text (never your API key) and the `request_id` from transcription calls.

---

## Security and costs

- **Your API key is a secret.** Don't paste it into chats, commit it, or share config files containing it. Prefer `~/.gnani/credentials` or an environment variable referenced from your config. If a key leaks, stop using it and ask Gnani (support@gnani.ai) to replace it, then update every place you set it.
- **HTTP mode has no login of its own.** Keep it on `127.0.0.1`.
- **Project-level configs are shared.** `.cursor/mcp.json` and `.mcp.json` often get committed. Keep keys out of them.
- **Your audio leaves your computer.** Files you transcribe are uploaded to the Gnani API. Don't use sensitive recordings unless that's acceptable under your organization's policies.
- **The server runs with your permissions.** It reads any file path the agent gives it and writes audio to the output folder. Review tool calls when unsure.
- **Requests count against your Gnani account.** Every transcription and synthesis is made with your key, and expressive tags are billable characters. A request to "try all the voices" makes many calls.

---

## License

[MIT](LICENSE)
