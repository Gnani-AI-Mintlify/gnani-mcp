# Gnani MCP Server — User Guide

Speech-to-Text, Text-to-Speech and Voice Cloning for Indian languages, inside your AI coding agent.

**Package:** `gnani-mcp` (v0.2.2) · **License:** MIT · **Works with:** Cursor, Claude Code, Claude Desktop, Codex, and any other MCP-capable client

---

## Contents

1. [What is this?](#1-what-is-this)
2. [Before you start](#2-before-you-start)
3. [Installation and API key setup](#3-installation-and-api-key-setup)
4. [Connect it to your coding agent](#4-connect-it-to-your-coding-agent)
5. [Using it: example prompts](#5-using-it-example-prompts)
6. [Tool reference](#6-tool-reference)
7. [Languages, models and voices](#7-languages-models-and-voices)
8. [Settings](#8-settings)
9. [Troubleshooting](#9-troubleshooting)
10. [Security and costs](#10-security-and-costs)

---

## 1. What is this?

### A 60-second introduction to MCP

**MCP (Model Context Protocol)** is a standard way for AI assistants to use outside tools. Without it, an assistant like Cursor or Claude can only read and write text and code. With it, you can plug in a small program, called an **MCP server**, that gives the assistant new abilities. The assistant sees a list of **tools** (named actions with inputs and outputs) and decides when to call them based on what you ask.

You never call the tools yourself. You write a normal request such as *"Transcribe `/Users/me/call.wav` in Hindi"*, and the assistant works out which tool to use, fills in the parameters, runs it and shows you the result.

```
You
 │  "Transcribe call.wav in Hindi"
 ▼
Coding agent (Cursor / Claude / Codex)     picks a tool and fills in its inputs
 │
 ▼
Gnani MCP server
 │
 ▼
Gnani speech API                           uses your API key
```

### What the Gnani MCP server adds

| Capability | What you can ask for |
|---|---|
| **Speech-to-Text (STT)** | Transcribe recordings in 10 Indian languages, from short clips to 4-hour files |
| **Text-to-Speech (TTS)** | Generate natural-sounding speech from text. There are two voice models (42 voices on Timbre v2.5 and 34 on Timbre v3.0), 76 voices in total |
| **Voice cloning** | Record a short sample of a voice, then generate new speech in that voice |

The server runs **on your own computer**. It reads audio files from your disk, sends them to the Gnani API, and saves any generated audio back to your disk.

---

## 2. Before you start

You need three things.

### 2.1 A Gnani API key

1. Sign up or log in at **[app.gnani.ai](https://app.gnani.ai)**.
2. Copy your API key. Treat it like a password.

You'll paste this key into your setup in a later step. [Section 3.2](#32-setting-your-api-key) explains exactly where it goes and how to confirm the server can see it.

### 2.2 A way to download and start the server

**What this step is for.** The Gnani MCP server is a small program written in Python. Your coding agent doesn't come with it, so something on your computer has to download it and start it whenever the agent needs it. This step installs that "something". You need **one** of the two options below, not both. Your choice only changes the *command* you'll put in your agent's configuration in [section 4](#4-connect-it-to-your-coding-agent).

| | Option 1: `uv` (recommended) | Option 2: Python and `pip` |
|---|---|---|
| What it is | A small tool that downloads and runs Python programs for you | The standard Python installer |
| Why choose it | You install one thing and never think about Python. The agent runs the server with `uvx gnani-mcp`. | You already use Python 3.10 or newer, or can't install `uv` |
| Command in your agent's config | `uvx` | The full path to the installed `gnani-mcp` program (see [3.1](#31-install-the-server)) |

If you're not sure, choose Option 1.

#### Option 1: install `uv`

Run **one** of these in a terminal, depending on your computer.

macOS with Homebrew:

```bash
brew install uv
```

macOS or Linux, without Homebrew:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then **close the terminal and open a new one**, so it can find the new program, and check that it worked:

```bash
uv --version
```

You should see a version number. Installing `uv` also installs `uvx`, the command your agent will use.

#### Option 2: Python and `pip`

Choose this only if you can't use `uv`. The server needs **Python 3.10 or newer**.

1. Check whether you already have it: run `python3 --version` (on Windows, `python --version`). If it shows 3.10 or higher, you're done with this step. Don't download anything.
2. If not, download and install Python from [python.org/downloads](https://www.python.org/downloads/), then open a new terminal and check again.
3. You'll install the server itself with `pip` in [section 3.1](#31-install-the-server).

### 2.3 A supported coding agent

Any MCP-capable agent works. This guide has step-by-step instructions for **Cursor**, **Claude Code**, **Claude Desktop** and **Codex**.

---

## 3. Installation and API key setup

### 3.1 Install the server

**If you chose Option 1 (`uv`) in section 2.2, there is nothing to install here.** Your agent runs `uvx gnani-mcp`, which downloads and starts the server on demand. Skip ahead to **[3.2](#32-setting-your-api-key)**, because that is where most first-time problems come from.

**If you chose Option 2 (Python and `pip`), install the server now.** Use a virtual environment (a private folder of Python packages that won't clash with anything else on your computer):

```bash
python3 -m venv ~/.gnani-mcp-venv
~/.gnani-mcp-venv/bin/pip install gnani-mcp
```

On Windows (PowerShell):

```powershell
python -m venv $HOME\.gnani-mcp-venv
$HOME\.gnani-mcp-venv\Scripts\pip install gnani-mcp
```

The server program is then at `~/.gnani-mcp-venv/bin/gnani-mcp` (Windows: `%USERPROFILE%\.gnani-mcp-venv\Scripts\gnani-mcp.exe`). When a config below says `"command": "uvx"`, use this full path instead and drop the `args` line.

**Check the install:**

```bash
~/.gnani-mcp-venv/bin/gnani-mcp --help
```

You should see the usage text. This only proves the program is installed. It doesn't check your API key. Section 3.3 shows how to do that.

### 3.2 Setting your API key

If you've tried running the server yourself and weren't sure where the API key goes, this section is for you.

#### Why the key is a bit tricky

The Gnani server needs your API key every time it talks to the Gnani API. The key isn't built in, and the server is **not** something you type your key into. Instead:

- Your coding agent (Cursor, Claude, Codex) **starts the server as a separate background program**.
- A program only knows what it is handed when it starts. It does not look at what you typed in your terminal earlier, and it can't ask you for the key.
- So the key has to be placed where the server will look for it **at the moment it starts**.

Think of it like a staff member who is given an envelope with the key when they begin their shift. If the envelope isn't there, they can still turn up for work, but every request they make to Gnani will fail.

#### What is an "environment variable"?

An **environment variable** is a named setting that is handed to a program when it starts, such as `GNANI_API_KEY` = `sk_abc123…`. MCP configs have an `env` block for exactly this. When your agent starts the Gnani server, it fills the server's environment with whatever you listed there.

#### Where the server looks (in this order)

| Order | Place | Typical use |
|---|---|---|
| 1 | The **`GNANI_API_KEY` environment variable** of the server process | The `env` block in your agent's config (what section 4 uses) |
| 2 | The file **`~/.gnani/credentials`** | A one-time setup that works with every agent and keeps the key out of config files |

The first one found wins, so a stale key in your config overrides a correct key in the file. If neither is found, the server still starts. Every tool call that needs the API then fails with a message telling you the key is missing.

#### Method A: put it in your agent's config (simplest)

This is what every example in [section 4](#4-connect-it-to-your-coding-agent) does:

```json
"env": {
  "GNANI_API_KEY": "YOUR_GNANI_API_KEY"
}
```

Replace `YOUR_GNANI_API_KEY` with your real key, inside the quotes, with no spaces. Save the file, then restart the agent (or reload its MCP servers) so the server is started again with the new setting.

#### Method B: the credentials file (recommended if you use several agents, or share your config)

Create the file once and every agent picks it up. You then don't need an `env` block at all.

macOS / Linux:

```bash
mkdir -p ~/.gnani
printf 'api_key = YOUR_GNANI_API_KEY\n' > ~/.gnani/credentials
chmod 600 ~/.gnani/credentials
```

Windows (PowerShell):

```powershell
New-Item -ItemType Directory -Force "$HOME\.gnani" | Out-Null
Set-Content "$HOME\.gnani\credentials" 'api_key = YOUR_GNANI_API_KEY'
```

The file ends up at `~/.gnani/credentials`, which on Windows is `C:\Users\<your name>\.gnani\credentials`. The format is strict:

- The line must be **`api_key = your-key`**, with the name `api_key` in lowercase. Don't write `GNANI_API_KEY=…` here. That line is silently ignored.
- Quotes around the key are allowed. Don't add `export`.
- Blank lines and lines starting with `#` are ignored.

#### Method C: a variable in your terminal (only for running things by hand)

macOS / Linux (bash or zsh):

```bash
export GNANI_API_KEY="YOUR_GNANI_API_KEY"
```

Windows (PowerShell): `$env:GNANI_API_KEY = "YOUR_GNANI_API_KEY"` · Windows (cmd): `set GNANI_API_KEY=YOUR_GNANI_API_KEY`

This only lasts for that one terminal window, and only programs started from it can see it. **Don't rely on it for your agent.** Cursor, Claude Desktop and similar apps are usually launched from the Dock, Start menu or Spotlight, not from your terminal, so they never see it. Use Method A or B for agents.

#### Common mistakes

| What happened | Why | Fix |
|---|---|---|
| I ran `gnani-mcp --api-key=MYKEY` and it still says the key is missing | `--api-key` is **only** used together with `--print`, to write the key into the config snippet it prints. It doesn't set the key for a running server. | Use Method A, B or C. |
| I put `GNANI_API_KEY=…` in `~/.gnani/credentials` and nothing happened | The file wants `api_key = …`. The other line is ignored. | Change it to `api_key = your-key`. |
| I ran `export GNANI_API_KEY=…`, but my desktop agent can't see it | The app wasn't started from that terminal. | Put the key in the agent's `env` block or in the credentials file. |
| I edited the config but nothing changed | The server was already running with the old settings. | Restart the agent (for Claude Desktop, quit it fully) or reload its MCP servers. |
| I still get `401` after setting it | The key has a typo or extra spaces or line breaks, the placeholder text (`YOUR_GNANI_API_KEY`, `your-api-key`) is still there, or a different, older key in the config is overriding the file. | Re-copy the key from [app.gnani.ai](https://app.gnani.ai) and check both places. |

### 3.3 Check that the server can see your key

Once you've connected your agent ([section 4](#4-connect-it-to-your-coding-agent)), ask it to make a call that needs your key:

> *"List my recent Gnani batch transcription jobs."*

This asks the Gnani API for your list of jobs. It doesn't process any audio. What you get back tells you where things stand:

| What you get | What it means |
|---|---|
| A list of jobs (it may be empty if you haven't run any) | The server found your key and the Gnani API accepted it. You're set. |
| `GNANI_API_KEY is not set. Add it to your MCP config (env.GNANI_API_KEY) or to ~/.gnani/credentials.` | The server didn't find a key. Go back to [3.2](#32-setting-your-api-key), then restart your agent. |
| `[HTTP 401 INVALID_API_KEY] Unauthorized` | The server found a key, but the Gnani API rejected it. Re-copy the key from [app.gnani.ai](https://app.gnani.ai) and check both places it can be set. |

Don't use *"list the voices"* as your test. That tool reads a built-in catalog and works even with no key at all.

**Optional: see what the server sees.** If you started the server yourself in a terminal (see [3.4](#34-running-the-server-by-hand-optional)), it prints a line like this when it starts:

```
gnani-mcp ready · v0.2.2 · base_url=https://api.vachana.ai · output_path=/Users/you/Desktop · auth=configured
```

`auth=configured` means a key was found. `auth=missing — set GNANI_API_KEY or ~/.gnani/credentials` means it wasn't. This only shows that *some* key was found. It doesn't prove the key is valid, so the call above is the real test. Agents that keep logs (for example Cursor's **MCP Logs**) show the same line.

### 3.4 Running the server by hand (optional)

You don't need this section for normal use.

#### What "running it" actually means

Your agent starts the server when it needs it and stops it when it's done, talking to it through the server's **standard input and output** (this is called the *stdio transport*). That's why a server you start by hand in a terminal looks idle after printing its log line: it's waiting for an agent to speak to it. Press `Ctrl+C` to stop it.

#### Run it as a local web service (HTTP)

Some clients want a web address instead of a command. In that case you start the server yourself:

```bash
GNANI_API_KEY="YOUR_GNANI_API_KEY" gnani-mcp --transport http --host 127.0.0.1 --port 8000 --path /mcp
```

(PowerShell: `$env:GNANI_API_KEY = "YOUR_GNANI_API_KEY"; gnani-mcp --transport http --port 8000`.) Then point your client at `http://127.0.0.1:8000/mcp`. In Cursor, for example:

```json
{ "mcpServers": { "gnani": { "url": "http://127.0.0.1:8000/mcp" } } }
```

Two things differ from the usual setup:

- **The key goes to the server, not the client.** In HTTP mode, you start the server, so the key must be in the environment of the terminal that starts it, or in `~/.gnani/credentials`. Putting it in the client's config does nothing.
- **There is no login on the web address.** Anyone who can reach that port can use your Gnani account through the server. Keep `--host 127.0.0.1` so only your own computer can connect, and don't expose the port to a network.

---

## 4. Connect it to your coding agent

Every agent needs the same three pieces of information:

| Setting | Value |
|---|---|
| **Command** | `uvx` (or the full path to `gnani-mcp` if you installed with pip) |
| **Arguments** | `gnani-mcp` |
| **Environment** | `GNANI_API_KEY` set to your key (optional if you use the credentials file) |

Replace `YOUR_GNANI_API_KEY` in every example below with your real key. Not sure what "environment" means here, or you'd rather not put the key in a config file? See [section 3.2](#32-setting-your-api-key) for all the ways to supply it.

### 4.1 Cursor

**Option A: edit the config file.**

- Global (all projects): `~/.cursor/mcp.json` (Windows: `%USERPROFILE%\.cursor\mcp.json`)
- One project only: `.cursor/mcp.json` inside the project

Create the file if it doesn't exist, or add the `gnani` entry inside an existing `mcpServers` block:

```json
{
  "mcpServers": {
    "gnani": {
      "command": "uvx",
      "args": ["gnani-mcp"],
      "env": {
        "GNANI_API_KEY": "YOUR_GNANI_API_KEY"
      }
    }
  }
}
```

**Option B: keep the key out of the file.** Cursor can read it from an environment variable on your machine:

```json
"env": { "GNANI_API_KEY": "${env:GNANI_API_KEY}" }
```

You can also rely on `~/.gnani/credentials` and leave out `env` entirely.

**Check that it worked:**
1. Open Cursor's Customize panel (or Settings → MCP). `gnani` should be listed and switched on, showing 10 tools.
2. If it isn't, open the Output panel (`Cmd/Ctrl+Shift+U`) and choose **MCP Logs** from the dropdown.

Cursor asks for your approval the first time the agent uses each tool. Click through to allow it, or add the tools to your auto-run list.

### 4.2 Claude Code (terminal)

**Option A: one command (easiest).** `--env` goes after the server name, before the `--`:

```bash
claude mcp add gnani --env GNANI_API_KEY=YOUR_GNANI_API_KEY -- uvx gnani-mcp
```

**Option B: use a config file.** Yes, Claude Code keeps its MCP servers in files too. The command above simply writes the entry for you. Where it goes depends on the *scope* you choose with `--scope`:

| Scope | Where it's stored | Who can use it |
|---|---|---|
| `local` (the default) | `~/.claude.json`, under the current project's folder | Only you, only in that project |
| `project` | `.mcp.json` in the project's root folder | Everyone who has the project (the file is meant to be committed to Git) |
| `user` | `~/.claude.json` | Only you, in all your projects |

The most convenient file to write yourself is a project's `.mcp.json`. Create it in the project's root folder (the same `mcpServers` layout that Cursor uses):

```json
{
  "mcpServers": {
    "gnani": {
      "command": "uvx",
      "args": ["gnani-mcp"]
    }
  }
}
```

Notes:

- **Keep the key out of this file**, because it's usually committed. Leave `env` out and let the server read the key from `~/.gnani/credentials` ([section 3.2](#32-setting-your-api-key)). Claude Code also lets a `.mcp.json` entry read a variable from your own environment, for example `"env": { "GNANI_API_KEY": "${GNANI_API_KEY}" }`. If that variable isn't set, Claude Code only warns and passes the literal text `${GNANI_API_KEY}` to the server, which then fails with a `401`.
- The first time you start `claude` in a project that has a `.mcp.json`, Claude Code asks you to approve its servers. Until you do, `claude mcp list` shows the server as *Pending approval*.
- `~/.claude.json` (used by the `local` and `user` scopes) also stores other Claude Code information, so the safest way to change it is the command. `claude mcp add-json` takes the entry as JSON text, for example `claude mcp add-json gnani '{"command":"uvx","args":["gnani-mcp"]}'`.

**Check that it worked:**

```bash
claude mcp list
```

You should see `gnani` with a `✔ Connected` status. Inside a Claude Code session, type `/mcp` to see the server and its tools.

### 4.3 Claude Desktop

1. Open the config file:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

   (In Claude Desktop you can also reach it via Settings → Developer → Edit Config.)
2. Add the server:

   ```json
   {
     "mcpServers": {
       "gnani": {
         "command": "uvx",
         "args": ["gnani-mcp"],
         "env": {
           "GNANI_API_KEY": "YOUR_GNANI_API_KEY"
         }
       }
     }
   }
   ```

3. **Fully quit and reopen** Claude Desktop. Closing the window isn't enough.
4. Start a new chat. The tools icon in the message box should list the `gnani` tools.

> Desktop apps sometimes can't find `uvx` because they don't inherit your terminal's `PATH`. If you see a "command not found" or "spawn uvx ENOENT" error, replace `"uvx"` with its full path. Find it with `which uvx` (macOS/Linux) or `where uvx` (Windows).

### 4.4 Codex (CLI, IDE extension and app)

All Codex surfaces share one configuration.

**Option A: one command**

```bash
codex mcp add gnani --env GNANI_API_KEY=YOUR_GNANI_API_KEY -- uvx gnani-mcp
```

**Option B: edit `~/.codex/config.toml`** (or `.codex/config.toml` inside a trusted project):

```toml
[mcp_servers.gnani]
command = "uvx"
args = ["gnani-mcp"]
startup_timeout_sec = 60     # the first run downloads the package
tool_timeout_sec = 1800      # long transcriptions can take many minutes

[mcp_servers.gnani.env]
GNANI_API_KEY = "YOUR_GNANI_API_KEY"
```

The two timeout lines matter. Codex gives a server **10 seconds** to start and a tool call **60 seconds** to finish by default. The first `uvx` run can take longer than 10 seconds, and batch transcription of long audio takes minutes.

**Check that it worked:** type `/mcp` in the Codex composer or terminal UI to see active servers.

### 4.5 Other agents (Windsurf, VS Code, Zed, and so on)

Any client that supports MCP **stdio** servers works with the same three values (command, args, env). The file location and wrapper key differ by client, so check your client's MCP documentation. The server entry itself looks like this:

```json
{ "command": "uvx", "args": ["gnani-mcp"], "env": { "GNANI_API_KEY": "YOUR_GNANI_API_KEY" } }
```

**Zed:** open the settings file (`zed: open settings file`, or Settings → AI → MCP Servers → *Add Server*) and add the entry under `context_servers` (not `mcpServers`), with `command`, `args` and `env` directly inside it:

```json
{
  "context_servers": {
    "gnani": {
      "command": "uvx",
      "args": ["gnani-mcp"],
      "env": { "GNANI_API_KEY": "YOUR_GNANI_API_KEY" }
    }
  }
}
```

In Settings → AI → MCP Servers, a green dot next to `gnani` means the server is active.

**Windsurf:** in the Cascade panel, open the MCPs menu and choose *Open MCP config file*, then add the entry under `mcpServers` (same JSON as Cursor). The file is `~/.config/devin/mcp_config.json` on macOS/Linux and `%APPDATA%\devin\mcp_config.json` on Windows; older installs use `~/.codeium/windsurf/mcp_config.json`. Press the refresh button in the MCP panel after saving.

The server can also run as a network service for clients that need a URL: `gnani-mcp --transport http --port 8000` serves it at `http://127.0.0.1:8000/mcp`.

**Tip:** `uvx gnani-mcp --print` (or `gnani-mcp --print` if installed) prints a ready-made config snippet you can copy.

### 4.6 Compatibility

| Agent | Status |
|---|---|
| Cursor | Tested with this server |
| Claude Code, Codex | Commands and config follow each vendor's current MCP documentation |
| Claude Desktop, Zed, Windsurf | Config follows each vendor's current MCP documentation |
| Other clients | Any client supporting MCP stdio servers should work |

---

## 5. Using it: example prompts

Once connected, just ask in plain English. You don't have to mention tool names, although you can. Always give **full file paths** (like `/Users/me/audio/call.wav`) so the agent and server can find your files.

> Generated audio is saved as a file on your computer, and the tool's response includes the file's location (by default your **Desktop**; see [Settings](#8-settings)). Open the file to listen to it.

### Transcribe a recording

- *"Transcribe `/Users/me/audio/customer-call.wav`. It's in Hindi."*
- *"Transcribe this clip and detect the language automatically: `/Users/me/audio/clip.mp3`. Use the newest model."*
  (Automatic language detection is a Prisma v3.0 feature, selected with the language setting `indic-auto`.)
- *"Transcribe `/Users/me/audio/sales-call.wav` in Hindi, and make sure these words are spelled right: Gnani, Vachana, Prisma."*
- *"Transcribe this meeting recording, keeping English words in English letters: `/Users/me/meeting.m4a`. The language is Hindi mixed with English."*

### Transcribe long audio

- *"This is a 2-hour call recording: `/Users/me/audio/long-call.mp3`. Transcribe it in Tamil and tell me who said what."* (turns on speaker separation)
- *"Transcribe the audio at https://example.com/recordings/call-42.wav in English and separate the speakers."*
- *"The recording is noisy because it's from a call centre. Clean it up before transcribing: `/Users/me/audio/noisy.wav`."*
- *"Show me my recent batch transcription jobs, then give me the transcript of the last completed one."*

### Generate speech

- *"Read this out in a Hindi female voice and save it as an MP3: 'नमस्ते, गनानी में आपका स्वागत है।'"*
- *"What voices are available for Telugu? Describe the options."*
- *"Read this Tamil sentence aloud in a female voice: …"*
- *"Read this Tamil sentence aloud in a male voice: …"* (There are no male Tamil voices on Timbre v2.5, so the agent needs to use a Timbre v3.0 voice, which speaks every language. See [section 7](#7-languages-models-and-voices).)
- *"Say this with a laugh in the middle, using a female voice on the newest voice model: 'Let me check… `<laugh>` found it!'"* (Expressive tags only work on Timbre v3.0.)
- *"Make an 8 kHz telephone-quality version of this announcement for a call-centre IVR."*

### Clone a voice

- *"Here's a 15-second sample of my voice: `/Users/me/audio/my-voice.wav`. Create a voice profile from it."*
- *"Using that voice profile, read this paragraph aloud: …"*
- *"Using the same voice profile, read this second paragraph too: …"*

### Combine tasks

- *"Transcribe `/Users/me/call.wav` in Hindi, summarize it in three bullets, then read the summary back as audio in a female English voice."*
- *"Read this script aloud with a Hindi voice, then transcribe the result and check that the text matches."*

### Tips for better results

- **Name the language.** Say "in Hindi" or "in Tamil", or ask for automatic detection.
- **Match the length to the tool.** Clips of up to 30 seconds can be transcribed in a single step. Longer audio goes through batch transcription, where the server creates a job and checks on it every 10 seconds until it finishes, so be patient.
- **For voice cloning, use clean audio.** The Gnani docs ask for 5–30 seconds of clear speech. The tool's own guidance is that 10–30 seconds of one person speaking, with little background noise, gives the best results.
- **For text-to-speech, pick a voice first.** Ask *"What voices do you have for Hindi?"* and then choose one. A voice belongs to one voice model, so a voice from the other model will be rejected.
- **Be specific about the output.** You can ask for the file type (WAV, MP3 and more), the sample rate and the speaking speed.

---

## 6. Tool reference

The server provides **10 tools**. You normally ask in plain English and the agent chooses the tool. This section tells you what each one can do, which options exist, and what comes back.

| # | Tool | In one line |
|---|---|---|
| 1 | `gnani_stt_transcribe` | Transcribe a short clip (up to 30 s) right away |
| 2 | `gnani_stt_batch_transcribe` | Transcribe long audio (up to 4 h) or a URL, start to finish |
| 3 | `gnani_stt_batch_list_jobs` | List your batch jobs |
| 4 | `gnani_stt_batch_status` | Check on a batch job |
| 5 | `gnani_stt_batch_get_transcripts` | Download the transcripts of a finished batch job |
| 6 | `gnani_stt_batch_cancel` | Cancel a running batch job |
| 7 | `gnani_tts_synthesize` | Turn text into speech |
| 8 | `gnani_tts_list_voices` | Browse the available voices |
| 9 | `gnani_vc_generate_embedding` | Create a voice profile from a sample (cloning, step 1) |
| 10 | `gnani_vc_synthesize` | Speak text in a cloned voice (cloning, step 2) |

### Speech-to-Text models

| | **Prisma v2.5** (default) | **Prisma v3.0** |
|---|---|---|
| Language | You choose exactly one language | One model for all 10 languages; can auto-detect, or take 1–4 language hints |
| Output styles | `verbatim`, `transcribe` | `verbatim`, `transcribe`, `codemix`, and `transliterate` (short clips only) |
| Extras | Native-script numerals (`itn_native_numerals`) | Context hints: `keyterms`, `topic`, `previous_text`, `speaker_names`; reports `detected_language_code` |

Output styles in plain words:

- **verbatim:** numbers spelled out as words, English words written in the native script.
- **transcribe:** numbers, currency and dates in their usual written form (for example ₹5,000).
- **codemix** (v3.0): English words stay in English letters, so Hinglish reads naturally.
- **transliterate** (v3.0, short clips only): the whole transcript in Latin letters.

Find-and-replace on the final text (see `enable_substitution` below) is offered with both models.

If you leave the style unspecified, v2.5 uses `verbatim`, while v3.0 uses `transcribe` for a single `hi-IN` or `en-IN` language and `verbatim` otherwise. To keep output consistent when switching models, ask for a style explicitly.

---

### 1. `gnani_stt_transcribe`: transcribe a short clip

Transcribes audio up to **30 seconds** and returns the text immediately.

| Parameter | Required | What it means |
|---|---|---|
| `audio_path` | one of three | Full path to a local file |
| `audio_base64` | one of three | Audio data encoded as base64 (needs `filename`) |
| `audio_url` | one of three | Direct link to an audio file (needs `filename`) |
| `filename` | with base64/URL | Name with extension, such as `clip.wav`, so the service knows the format |
| `language_code` | usually | v2.5: one code such as `hi-IN`. v3.0: `indic-auto` or up to 4 codes, such as `hi-IN,en-IN`. Optional only with v3.0 `transliterate`. |
| `model` | no | `prisma-v2.5` (default) or `prisma-v3.0` |
| `format` | no | `verbatim`, `transcribe`, `codemix` (v3.0), `transliterate` (v3.0) |
| `keyterms` | no | v3.0: names and terms to spell correctly (up to 200) |
| `topic` | no | v3.0: a description of the recording (up to 1,600 characters) |
| `previous_text` | no | v3.0: the transcript of the clip just before this one, for recordings cut into pieces (the last 600 characters are used) |
| `speaker_names` | no | v3.0: 1–4 names that may be spoken (a spelling aid, not speaker separation) |
| `itn_native_numerals` | no | v2.5 only, with `format` set to `transcribe`: write digits in the native script (for example ₹५,००० instead of ₹5,000 for Hindi) |
| `enable_substitution` + `substitution_map` | no | Find-and-replace on the final text, after recognition (up to 10 rules). Each rule lists the words to find and the replacement, for example replace "ok" and "okay" with "acknowledged" |

**Audio formats:** WAV, MP3, OGG, FLAC, AAC, M4A.
**Size limit:** audio you send as base64 or fetch from a link can be at most 25 MB (the server checks this before uploading).
**Returns:** `transcript`, `model`, `request_id`, and (v3.0) `detected_language_code`.

---

### 2. `gnani_stt_batch_transcribe`: transcribe long audio

For recordings up to **4 hours**. One call does everything: it creates the job, starts it, checks progress every 10 seconds (up to 30 minutes) and fetches the transcripts. **The agent waits while this runs**, so expect it to take roughly as long as the job takes.

| Parameter | Required | What it means |
|---|---|---|
| `language_code` | yes | v2.5: one code, or up to 3 codes for per-file language detection. v3.0: `indic-auto` or 1–4 codes. |
| `audio_path` | one of two | Local file (**max 10 MB** when uploaded this way) |
| `audio_url` | one of two | Public web link to the audio file (no size limit, but 4 hours maximum) |
| `model` | no | `prisma-v2.5` (default) or `prisma-v3.0` |
| `with_diarization` | no | Separate speakers ("who said what") |
| `num_speakers` | no | The most speakers to separate, 1–8. It's an upper limit, not a target. |
| `with_denoise` | no | Clean up noisy audio first. Leave it off for clean recordings, where it only adds processing time. |
| `is_multi_channel` | no | Only for true multi-channel files |
| `format` | no | v3.0 only: `verbatim`, `transcribe`, `codemix` (`transliterate` isn't available for batch) |
| `keyterms`, `topic`, `speaker_names` | no | v3.0 only. Use **one** of: `keyterms`, `topic`, `topic` + `keyterms`, or `speaker_names`. `topic` must be 30–1,600 characters. |
| `callback_url` | no | HTTPS address that Gnani posts the results to when the job finishes (useful if you don't want to wait) |

**Audio formats:** WAV, MP3, MP4, FLAC, OGG, Opus, M4A, AAC, WebM, AMR.
**Returns:** `job_id`, `status`, `progress`, and a list of `transcripts` (one per file, with `full_transcript`, `language_code`, `duration_seconds` and time-stamped `segments`). If any file failed, a `warning` explains why.

If the call is cut short (for example, your agent times out), the job keeps running on Gnani's servers. Use tools 3–5 to pick it up.

---

### 3. `gnani_stt_batch_list_jobs`: list batch jobs

Shows your jobs, newest first. Handy for finding a `job_id` you've lost.

| Parameter | What it means |
|---|---|
| `status` | Only jobs in one state: `CREATED`, `STARTING`, `QUEUED`, `IN_PROGRESS`, `COMPLETED`, `PARTIAL_FAILURE`, `FAILED`, `START_FAILED`, `CANCELLING`, `CANCELLED` |
| `limit` | Page size, 1–100 (default 20) |
| `cursor` | To get the next page, pass the `next_cursor` from the previous response |

**Returns:** `jobs` and `pagination` (`has_more`, `next_cursor`).

### 4. `gnani_stt_batch_status`: check a job

| Parameter | What it means |
|---|---|
| `job_id` | The job to check |

**Returns:** `status`, `progress` (files completed and total), `config`, timestamps and, if applicable, `cancel_reason`. It does **not** include the transcript text.

### 5. `gnani_stt_batch_get_transcripts`: fetch finished transcripts

| Parameter | What it means |
|---|---|
| `job_id` | A job that has finished |

**Returns:** the same `transcripts` list as tool 2. For files that failed, you get the status and the reason. If the job isn't finished yet, you get a message saying so. Transcript download links expire after an hour; call the tool again for fresh ones.

### 6. `gnani_stt_batch_cancel`: cancel a job

| Parameter | What it means |
|---|---|
| `job_id` | The job to stop |

Works while a job is `CREATED`, `STARTING`, `QUEUED` or `IN_PROGRESS`. It has no effect on a job that has already finished.

---

### Text-to-Speech models

| | **Timbre v2.5** (default) | **Timbre v3.0** |
|---|---|---|
| Voices | 42, each with one preferred language | 34, each speaks **all 10 languages** |
| Expressive tags | Not supported (tags are removed, and you get a warning) | Supported, such as `<laugh>`, `<whispers>` |

**Voices are not shared between models.** A v2.5 voice name won't work with v3.0, or the other way round.

**Expressive tags (v3.0 only).** Put these inline in your text: `<laugh>`, `<giggle>`, `<sigh>`, `<exhales>`, `<sniffles>`, `<yawns>`, `<coughs>`, `<clears throat>`, `<whispers>`, `<shouting>`, `<excited>`, `<slow>`, `<pauses>`.
- A tag affects the speech from where it appears until the next tag.
- `<pauses>` adds silence and is never spoken.
- Tags count as billable characters.
- A tag the service doesn't know is removed from the text, and you get a warning listing the supported tags.

Numbers, currency, dates and IDs are converted to spoken form automatically, so write naturally.

### 7. `gnani_tts_synthesize`: text to speech

| Parameter | Required | What it means |
|---|---|---|
| `text` | yes | What to say |
| `voice` | yes | Voice name from the chosen model's catalog (not case-sensitive) |
| `model` | no | `timbre-v2.5` (default) or `timbre-v3.0` |
| `language` | no | `auto` (default, detects from the script), or `hi-IN`, `en-IN`, `hi-en` (Hinglish), `ta-IN`, `te-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `pa-IN`, `bn-IN`, `gu-IN`. With v2.5, match the voice's language. |
| `speed` | no | How fast the voice speaks. Optional: when you leave it out, the voice's recommended speed is used. **Timbre v3.0:** 0.8 to 1.2 (the service snaps it to 0.8, 1.0 or 1.2). **Timbre v2.5:** 0.85 to 1.15. A value outside the model's range is rejected before the API is called. 1.0 is normal. |
| `container` | no | File type: `wav` (default), `mp3`, `ogg` (Opus), `raw`, `mulaw`, `alaw`. `mulaw` and `alaw` are phone formats and always 8,000 Hz. |
| `sample_rate` | no | 8000, 16000, 22050, 24000, 44100 or 48000 Hz (default 48000) |
| `encoding` | no | `linear_pcm` (default), `pcm_s16le`, `pcm_mulaw`, `pcm_alaw`, `oggopus`. You rarely need to set this. |
| `bitrate` | no | MP3 only: `32k`, `64k`, `96k`, `128k`, `192k` |

If you ask for a voice that belongs to the other model, the tool stops before calling the API and tells you which model it belongs to.

**Returns:** `audio_file` (the saved file's full path), `size_bytes`, `model`, `voice`, `language`, `container`, `encoding`, `sample_rate`, and `warnings` if something was adjusted (for example, tags removed on v2.5).

### 8. `gnani_tts_list_voices`: browse voices

| Parameter | What it means |
|---|---|
| `model` | `timbre-v2.5` (default) or `timbre-v3.0` |
| `language` | v2.5 only: show voices for one language, such as `hi-IN` |
| `gender` | `Male` or `Female` |

**Returns:** `total_voices` and a `voices` list. Each voice has a `voice` name, `gender`, `language` (v3.0 voices show `all`), `persona` and `description`. For v3.0 it also returns the supported `languages` and `audio_tags`. This tool reads a catalog built into the server and makes no call to the Gnani API.

---

### Voice cloning

Cloning is a **two-step process**:

1. **Create a voice profile** (a "speaker embedding") from a short recording of the voice.
2. **Speak text in that voice**, as many times as you like, reusing the profile.

You only do step 1 once per voice. Ask your agent to keep the profile it returns and reuse it.

> **Only clone voices you have the right to use**, for example your own voice or one you have explicit permission for.

### 9. `gnani_vc_generate_embedding`: create the voice profile

Upload **5–30 seconds** of clean, single-speaker audio. The tool's guidance is that 10–30 seconds with little background noise works best.

| Parameter | What it means |
|---|---|
| `audio_path` / `audio_base64` / `audio_url` | Provide one: a local path, base64 data, or a link to the reference audio |
| `filename` | Name with extension; required with base64 or URL |

**Formats:** WAV, MP3, OGG, FLAC, AAC, M4A (as listed in the tool's description; the Gnani documentation's examples use WAV and MP3).
**Size limit:** audio sent as base64 or fetched from a link can be at most 25 MB.
**Returns:** `speaker_embedding`, an object holding `embedding` (a long text string), `shape` and `dtype`. Pass it unchanged to the next tool.

### 10. `gnani_vc_synthesize`: speak in the cloned voice

| Parameter | Required | What it means |
|---|---|---|
| `text` | yes | What to say |
| `speaker_embedding` | yes | The object returned by tool 9 |
| `container` | no | `wav` (default), `mp3`, `ogg`, `raw`, `mulaw`, `alaw` |
| `sample_rate` | no | 8000, 16000, 22050, 24000 or 44100 Hz (default 44100) |
| `encoding` | no | `linear_pcm` (default), `pcm_s16le`, `pcm_mulaw`, `pcm_alaw`, `oggopus` |
| `bitrate` | no | MP3 only: `96k`, `128k`, `192k` |

**Returns:** `audio_file` (the saved file's full path), `size_bytes`, `container`, `encoding`, `sample_rate`, and `warnings` if any.

---

## 7. Languages, models and voices

### Speech-to-Text languages (both Prisma models)

| Language | Code | | Language | Code |
|---|---|---|---|---|
| Bengali | `bn-IN` | | Malayalam | `ml-IN` |
| English (India) | `en-IN` | | Marathi | `mr-IN` |
| Gujarati | `gu-IN` | | Punjabi | `pa-IN` |
| Hindi | `hi-IN` | | Tamil | `ta-IN` |
| Kannada | `kn-IN` | | Telugu | `te-IN` |

Prisma v3.0 also accepts `indic-auto` (detect the language) and comma-separated hints such as `hi-IN,en-IN`.

### Text-to-Speech languages

The same 10 languages as above (Timbre v3.0 voices speak all of them), plus `auto`, which detects the language from the script of your text. **Hinglish** (`hi-en`, a Hindi–English mix) is the preferred language of one Timbre v2.5 voice, Poorvi.

### Text-to-Speech voices

**Timbre v2.5** (42 voices; each has one preferred language)

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

**Timbre v3.0** (34 voices; every voice speaks all 10 languages)

- Female (18): Anitasingh, Chetana, Kalpana, Lakshmi, Lakshmidevi, Neelam, Priyasharm, Rajni, Rekha, Riyaa, Shivani, Shruthi, Sneha, Sohini, Sunaina, Swathi, Tarika, Vasudha
- Male (16): Arko, Avinash, Devansh, Harshad, Mahendra, Manjunath, Nitin, Prakash, Rahulmehta, Rajeev, Rakesh, Santosh, Shubham, Vikramdasu, Vinod, Yashraj

Ask the agent to run the voice list for each voice's persona and description. There are 76 voices in total (42 + 34), and no voice name appears in both lists.

---

## 8. Settings

You normally only need the API key. Everything else has a sensible default.

| Setting | Default | What it does |
|---|---|---|
| `GNANI_API_KEY` | none | **Required.** Your Gnani API key (or use `~/.gnani/credentials`). |
| `GNANI_MCP_BASE_PATH` | `~/Desktop` | Folder where generated audio files are saved. Set this to a project folder to keep your Desktop tidy. |
Set them in the `env` block of your agent's config, for example:

```json
"env": {
  "GNANI_API_KEY": "YOUR_GNANI_API_KEY",
  "GNANI_MCP_BASE_PATH": "/Users/me/projects/audio-output"
}
```

The folder is created if it doesn't exist. Files are named with the tool and the date and time (down to the microsecond), such as `gnani_tts_20261103_175002_945517.wav`. Voice-clone audio starts with `gnani_vc_`. Each call writes a new file.

---

## 9. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| The server doesn't appear in my agent | Config file in the wrong place or invalid JSON. Check for missing commas or quotes. Restart the agent (for Claude Desktop, fully quit it). |
| "command not found" / `spawn uvx ENOENT` | The agent can't find `uvx`. Install `uv`, open a new terminal, and use the full path from `which uvx` (Windows: `where uvx`) as the `command`. |
| Server shows as failed or times out on first start (Codex) | First launch downloads the package. Set `startup_timeout_sec = 60`. |
| Long transcription fails with a timeout | Your agent's tool timeout is too short. The batch tool can wait up to 30 minutes. In Codex, set `tool_timeout_sec = 1800`. In Claude Code, set the `MCP_TOOL_TIMEOUT` environment variable (in milliseconds) before starting it. The Gnani job keeps running either way: ask for the job's status or transcripts afterwards (tools 3–5 in [section 6](#6-tool-reference)). |
| `401` / "Unauthorized" / "INVALID_API_KEY" | The Gnani API rejected the key: it has a typo, extra spaces or quotes, or isn't a valid key. Re-copy it from [app.gnani.ai](https://app.gnani.ai). |
| `403` / `SCOPE_NOT_ALLOWED` | Your key was accepted but isn't allowed to use that product or model. Contact [support@gnani.ai](mailto:support@gnani.ai). |
| Error mentions `GNANI_API_KEY` or `~/.gnani/credentials` | No key was found. Add it to the config's `env` or to the credentials file ([section 3.2](#32-setting-your-api-key)), then restart the agent. |
| The log says `auth=missing` although I set the key | The key isn't reaching the server process. Common causes: you set it with `export` in a terminal but the agent was started elsewhere; the credentials file uses `GNANI_API_KEY=…` instead of `api_key = …`; or you used `--api-key` without `--print` (it's ignored). See [section 3.2](#32-setting-your-api-key). |
| The log says `auth=configured` but calls fail with `401` | A key was found, but it's wrong. Check for typos, spaces, a leftover placeholder, or an older key in the config that overrides the credentials file. Use the check in [section 3.3](#33-check-that-the-server-can-see-your-key). |
| I started the server by hand and it just sits there | That's normal. It's waiting for an agent to talk to it. Press `Ctrl+C` to stop it. See [section 3.4](#34-running-the-server-by-hand-optional). |
| My HTTP-mode server can't find the key | In HTTP mode the key must be set where you start the server (or in `~/.gnani/credentials`), not in the client's config. |
| "Audio file not found" | The path is wrong or relative. Use the full absolute path. |
| "Unsupported audio format" | For short-clip transcription and voice cloning, use WAV, MP3, OGG, FLAC, AAC or M4A. Batch transcription also accepts MP4, Opus, WebM and AMR. With base64 or URL input, make sure `filename` has the right extension. |
| "Unsupported language code" | Use a code from [section 7](#7-languages-models-and-voices), such as `hi-IN`. Prisma v2.5 accepts a single language. |
| "Voice 'X' is not available for timbre-…" | Voices belong to one model. The message names the model the voice belongs to and lists the valid voices. Switch the model, or pick another voice. |
| Audio tags were removed from my text | Tags only work with `timbre-v3.0`. Ask for that model. |
| Can't find the generated audio | Check the `audio_file` path in the response. The default folder is your Desktop. |
| A batch job seems stuck | Ask the agent to check the job's status, or list your recent jobs and cancel it if needed. |
| `429` (too many requests) | The server already retries up to 5 times with a short wait before giving up. If you still see it, wait a moment and try again, and avoid sending many requests at once. |
| `504` (timeout) or "did not respond within 120s" | The Gnani API took too long to answer. Try again. For long audio, use batch transcription instead. |
| The transcript is empty | Check that the clip contains speech and is not extremely short. Gnani's documentation sets a minimum clip length of 0.1 seconds. |

**Where to look for logs**
- **Cursor:** Output panel → **MCP Logs**
- **Claude Code:** run `claude mcp list` or `claude mcp get gnani`, and `/mcp` in a session
- **Codex:** `/mcp` in the composer or terminal UI
- **Any client:** the server writes its log lines to stderr, which most clients capture

**Still stuck?** Contact support at [support@gnani.ai](mailto:support@gnani.ai) and include the error text (never your API key). Note the `request_id` returned by transcription calls, since it helps support find your request.

---

## 10. Security and costs

- **Your API key is a secret.** Don't paste it into chats, commit it to Git, or share config files that contain it. Prefer the `~/.gnani/credentials` file, or an environment variable referenced from your config. If a key leaks, stop using it and ask Gnani ([support@gnani.ai](mailto:support@gnani.ai)) to replace it, then update every place you set it.
- **HTTP mode has no login of its own.** If you run the server with `--transport http`, anyone who can reach its address can use your Gnani account through it. Keep it on `127.0.0.1`.
- **Project-level configs are shared.** `.cursor/mcp.json` and `.mcp.json` often get committed. Keep keys out of them.
- **Your audio leaves your computer.** Files you transcribe or use as voice references are uploaded to the Gnani API. Don't use sensitive recordings unless that's acceptable under your organization's policies.
- **The server runs with your permissions.** It reads any file path the agent gives it and writes audio to the output folder. Review the agent's tool calls when you're unsure. Most agents show them and ask for approval.
- **Requests count against your Gnani account.** Every transcription, synthesis and clone request is made with your API key. In text-to-speech, expressive tags count as billable characters. A request to "try all the voices" makes many calls. Check your plan and usage in your Gnani account.
- **Cloning consent.** Only clone voices you own or have explicit permission to use.

---

*Gnani AI · [gnani.ai](https://gnani.ai) · [docs.gnani.ai](https://docs.gnani.ai)*
