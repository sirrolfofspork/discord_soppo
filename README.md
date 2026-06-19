# SOPPO_Python

A small **local Discord chatbot** that role-plays as a video game character. It reads messages in your **`#general`** channel (configurable), sends recent chat context plus the latest line to a configured LLM backend, and posts the reply back in character.

## Features

- **Secure token**: `DISCORD_BOT_TOKEN` from environment (via `.env` + `python-dotenv`).
- **Channel filter**: Prefer exact channel IDs via `DISCORD_ALLOWED_CHANNEL_IDS`; if unset, fall back to channel name via `DISCORD_CHANNEL_NAME` (default `general`), case-insensitive.
- **Ignores bots by default** and always ignores its own messages. Optional controlled bot-to-bot replies can be enabled with `RESPOND_TO_OTHER_BOTS=true` plus `BOT_AUTHOR_COOLDOWN_SECONDS` loop protection.
- **Rolling memory**: Recent unsummarized messages per channel (`MAX_CONTEXT_MESSAGES`) plus compact per-channel summaries when history exceeds `MAX_CONTEXT_MESSAGES_BEFORE_SUMMARY`, with a **character cap** (`MAX_PROMPT_CHARS`).
- **When it replies**:
  - **Always** when @mentioned, when replying to the bot’s message, or when someone uses **`!soppo`**.
  - **Sometimes** at random (`SPONTANEOUS_REPLY_CHANCE`, default **0.10**), with a **cooldown** after any reply (`REPLY_COOLDOWN_SECONDS`).
- **Safety-ish defaults**: Strips risky mass pings from model output; `allowed_mentions` disables `@everyone` / `@here` / user / role pings on sends.
- **Stub prompt** in `prompts.py` — replace placeholders with your real character.

## Requirements

- **Python 3.11+**
- A **Discord bot** application and token ([Discord Developer Portal](https://discord.com/developers/applications)).
- One configured LLM backend: **Ollama**, **LM Studio** OpenAI-compatible local server, or **OpenAI API**.

## Setup

### 1. Clone or copy this folder

```bash
cd SOPPO_Python
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment

```bash
copy .env.example .env
```

On macOS/Linux use `cp .env.example .env`.

Edit **`.env`**:

- Set **`DISCORD_BOT_TOKEN`** to your bot token.
- Set **`LLM_BACKEND`** to `ollama`, `lmstudio`, or `openai`.
- Adjust backend settings such as **`OLLAMA_MODEL`** / **`OLLAMA_URL`**, **`LMSTUDIO_BASE_URL`** / **`LMSTUDIO_MODEL`**, or **`OPENAI_API_KEY`** / **`OPENAI_MODEL`** as needed.
- Adjust **`DISCORD_ALLOWED_CHANNEL_IDS`** for exact per-server channel gating, or leave it empty and use **`DISCORD_CHANNEL_NAME`** as the legacy fallback. Adjust **`SPONTANEOUS_REPLY_CHANCE`**, **`REPLY_COOLDOWN_SECONDS`**, **`MAX_CONTEXT_MESSAGES`**, **`MAX_CONTEXT_MESSAGES_BEFORE_SUMMARY`**, **`SUMMARY_BATCH_SIZE`**, **`MAX_CHANNEL_SUMMARY_CHARS`**, **`MEMORY_STORE_PATH`**, **`MAX_PROMPT_CHARS`** if needed.

Channel filtering priority:

```env
# Exact channels, safest for multi-server deployments; takes priority when non-empty.
DISCORD_ALLOWED_CHANNEL_IDS=123456789012345678,234567890123456789

# Fallback only when DISCORD_ALLOWED_CHANNEL_IDS is empty.
DISCORD_CHANNEL_NAME=general
```

Use channel IDs when the bot is in more than one server. That prevents SOPPO from answering in every server that happens to have a `#general`, because of course every server does. Discord is imaginative like that.

Bot-author filtering:

```env
# Default: ignore other Discord bots. SOPPO always ignores herself either way.
RESPOND_TO_OTHER_BOTS=false

# Only applies after SOPPO replies to another bot author; humans are unaffected.
BOT_AUTHOR_COOLDOWN_SECONDS=60
```

Set `RESPOND_TO_OTHER_BOTS=true` only for controlled channels or bridge/testing setups. Other bot messages still have to pass the normal channel filter and trigger logic.

### 5. Discord bot settings

In the Developer Portal, under **Bot**:

- Enable **Privileged Gateway Intents** → **Message Content Intent** (required for reading message text).

Invite the bot with **applications.commands** (optional for later) and permissions to **Read Messages** / **Send Messages** in the target channel.

### 6. LLM backend

#### Ollama

Ensure Ollama is running and the model exists, for example:

```bash
ollama pull qwen3.5:4b
```

Default API base: `http://localhost:11434`.

#### LM Studio

Start LM Studio's local OpenAI-compatible server, load a model, then configure:

```env
LLM_BACKEND=lmstudio
LMSTUDIO_BASE_URL=http://localhost:1234/v1
LMSTUDIO_MODEL=<model-name>
LMSTUDIO_API_KEY=not-needed
```

The model name must match what LM Studio exposes through its local server.

#### OpenAI API

Configure:

```env
LLM_BACKEND=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.4-mini
```

## Run locally

With venv activated and `.env` in place:

```bash
python main.py
```

On startup you should see logs similar to:

- Bot **username** and id
- **Guilds** connected
- Allowed **channel IDs**, or monitored **channel name** fallback
- **Spontaneous reply chance** and **cooldown**
- Other-bot response mode and per-bot-author cooldown
- Channel summary memory threshold, batch size, and summary character cap

## Run as a user systemd service

A user-level service template is provided at:

```bash
deploy/soppo-discord.service
```

Install or refresh it on the Hermes Linux host with:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/soppo-discord.service ~/.config/systemd/user/soppo-discord.service
systemctl --user daemon-reload
systemctl --user enable --now soppo-discord.service
```

Operational commands:

```bash
systemctl --user status soppo-discord.service --no-pager
journalctl --user -u soppo-discord.service -f
systemctl --user restart soppo-discord.service
```

The service runs `.venv/bin/python main.py` from the project root. Secrets stay in the repo-local `.env`, loaded by `main.py`; do not put tokens in the unit file.

If `LLM_BACKEND=lmstudio`, LM Studio's local OpenAI-compatible server and the configured model still need to be available. SOPPO can be online while LM Studio is down, but replies will fail until the backend is restored.

## Project layout

| File | Role |
|------|------|
| `main.py` | Entry point: logging, `load_dotenv()`, `load_config()`, starts the bot |
| `config.py` | Reads env vars; tunable defaults documented at bottom of file |
| `bot.py` | Discord client, intents, `on_message`, history, summary-memory rollover, `should_respond` logic |
| `memory.py` | Channel-specific summary-memory helpers backed by `memory_store.py` |
| `memory_store.py` | Generic LangGraph-style namespace/key JSON memory store |
| `llm_client.py` | LLM backend router: Ollama, LM Studio, or OpenAI; prompt size trimming helper |
| `ollama_client.py` | Ollama `/api/chat` backend |
| `openai_client.py` | OpenAI-compatible chat completions backend used by OpenAI and LM Studio |
| `prompts.py` | SOPPO character prompt and prompt formatting helpers |
| `.env.example` | Template for `.env` |
| `requirements.txt` | Dependencies |

## Tuning cheat sheet

| What | Where |
|------|--------|
| Spontaneous reply chance | `.env` → `SPONTANEOUS_REPLY_CHANCE` |
| Cooldown after any reply | `.env` → `REPLY_COOLDOWN_SECONDS` |
| Respond to other Discord bots | `.env` → `RESPOND_TO_OTHER_BOTS` |
| Other-bot loop cooldown | `.env` → `BOT_AUTHOR_COOLDOWN_SECONDS` |
| Max unsummarized messages in memory | `.env` → `MAX_CONTEXT_MESSAGES` |
| Summary rollover threshold | `.env` → `MAX_CONTEXT_MESSAGES_BEFORE_SUMMARY` |
| Summary batch size | `.env` → `SUMMARY_BATCH_SIZE` |
| Max per-channel summary chars | `.env` → `MAX_CHANNEL_SUMMARY_CHARS` |
| Channel summary JSON store path | `.env` → `MEMORY_STORE_PATH` |
| Max context characters to LLM | `.env` → `MAX_PROMPT_CHARS` |
| Backend selection | `.env` → `LLM_BACKEND` |
| Ollama model name | `.env` → `OLLAMA_MODEL` |
| LM Studio endpoint/model | `.env` → `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL` |
| OpenAI model | `.env` → `OPENAI_MODEL` |
| Exact channel ID filter | `.env` → `DISCORD_ALLOWED_CHANNEL_IDS` |
| Channel name fallback | `.env` → `DISCORD_CHANNEL_NAME` |
| Character voice / rules | `prompts.py` → `build_system_prompt()` |
| Force reply command | Message containing **`!soppo`** (see `bot.py` → `message_has_trigger`) |

## Extending later

- **Slash commands**: add a `discord.app_commands.CommandTree` in `setup_hook` and sync to a guild or globally.
- **Per-channel behavior**: extend the existing `DISCORD_ALLOWED_CHANNEL_IDS` gate into per-channel settings or store settings in a dict / small DB.
- **Stronger “no repeat”**: adjust the `last_bot_reply` block in `prompts.py` or add similarity checks before send.

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `Missing or empty environment variable: DISCORD_BOT_TOKEN` | No `.env` or token not set; fix `.env` next to `main.py`. |
| Bot online but never reads text | **Message Content Intent** not enabled in the portal, or bot lacks **View Channel** / **Read Message History** in `#general`. |
| Bot ignores all messages | If `DISCORD_ALLOWED_CHANNEL_IDS` is set, the current channel ID is not in that list. If it is empty, the channel is not named like `DISCORD_CHANNEL_NAME` (default `general`), or messages are in a thread / wrong server. |
| Bot ignores another bot | `RESPOND_TO_OTHER_BOTS` defaults to `false`; set it to `true` only when you want other bots to pass normal channel and trigger checks. If enabled, `BOT_AUTHOR_COOLDOWN_SECONDS` may still suppress rapid loops from the same bot author. |
| `Could not reach Ollama` | Ollama not running, wrong `OLLAMA_URL`, or firewall blocking `localhost:11434`. |
| Could not reach LM Studio / connection failed | LM Studio local server is not running, wrong `LMSTUDIO_BASE_URL`, or no model is loaded. |
| `model '…' not found` / HTTP 404 | That tag is not installed. Run `ollama pull <OLLAMA_MODEL>` or set `OLLAMA_MODEL` to a name from `ollama list`. |
| Replies too spammy / too quiet | Lower or raise `SPONTANEOUS_REPLY_CHANCE`; increase `REPLY_COOLDOWN_SECONDS`. |
| `!soppo` does nothing | Must appear as its own token (regex word boundary); not inside another word. |

## License

Use and modify for your own projects; no license file is included by default.
