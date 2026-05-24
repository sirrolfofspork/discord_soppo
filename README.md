# SOPPO_Python

A small **local Discord chatbot** that role-plays as a video game character. It reads messages in your **`#general`** channel (configurable), sends recent chat context plus the latest line to a **local Ollama** model, and posts the reply back in character.

## Features

- **Secure token**: `DISCORD_BOT_TOKEN` from environment (via `.env` + `python-dotenv`).
- **Channel filter**: Only channels whose name matches `DISCORD_CHANNEL_NAME` (default `general`), case-insensitive.
- **Ignores bots** and its own messages.
- **Rolling memory**: Last N messages per channel (`MAX_CONTEXT_MESSAGES`), with a **character cap** (`MAX_PROMPT_CHARS`).
- **When it replies**:
  - **Always** when @mentioned, when replying to the bot’s message, or when someone uses **`!soppo`**.
  - **Sometimes** at random (`SPONTANEOUS_REPLY_CHANCE`, default **0.10**), with a **cooldown** after any reply (`REPLY_COOLDOWN_SECONDS`).
- **Safety-ish defaults**: Strips risky mass pings from model output; `allowed_mentions` disables `@everyone` / `@here` / user / role pings on sends.
- **Stub prompt** in `prompts.py` — replace placeholders with your real character.

## Requirements

- **Python 3.11+**
- A **Discord bot** application and token ([Discord Developer Portal](https://discord.com/developers/applications)).
- **Ollama** running locally, with a model pulled (e.g. `qwen3.5:4b`; must match `ollama list`).

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
- Adjust **`OLLAMA_MODEL`**, **`OLLAMA_URL`**, **`DISCORD_CHANNEL_NAME`**, **`SPONTANEOUS_REPLY_CHANCE`**, **`REPLY_COOLDOWN_SECONDS`**, **`MAX_CONTEXT_MESSAGES`**, **`MAX_PROMPT_CHARS`** if needed.

### 5. Discord bot settings

In the Developer Portal, under **Bot**:

- Enable **Privileged Gateway Intents** → **Message Content Intent** (required for reading message text).

Invite the bot with **applications.commands** (optional for later) and permissions to **Read Messages** / **Send Messages** in the target channel.

### 6. Ollama

Ensure Ollama is running and the model exists, for example:

```bash
ollama pull qwen3.5:4b
```

Default API base: `http://localhost:11434`.

## Run locally

With venv activated and `.env` in place:

```bash
python main.py
```

On startup you should see logs similar to:

- Bot **username** and id
- **Guilds** connected
- Monitored **channel name**
- **Spontaneous reply chance** and **cooldown**

## Project layout

| File | Role |
|------|------|
| `main.py` | Entry point: logging, `load_dotenv()`, `load_config()`, starts the bot |
| `config.py` | Reads env vars; tunable defaults documented at bottom of file |
| `bot.py` | Discord client, intents, `on_message`, history, `should_respond` logic |
| `llm_client.py` | Ollama `/api/chat` (non-streaming), prompt size trimming helper |
| `prompts.py` | **Character stub** — edit `build_system_prompt()` |
| `.env.example` | Template for `.env` |
| `requirements.txt` | Dependencies |

## Tuning cheat sheet

| What | Where |
|------|--------|
| Spontaneous reply chance | `.env` → `SPONTANEOUS_REPLY_CHANCE` |
| Cooldown after any reply | `.env` → `REPLY_COOLDOWN_SECONDS` |
| Max messages in memory | `.env` → `MAX_CONTEXT_MESSAGES` |
| Max context characters to Ollama | `.env` → `MAX_PROMPT_CHARS` |
| Model name | `.env` → `OLLAMA_MODEL` |
| Channel name filter | `.env` → `DISCORD_CHANNEL_NAME` |
| Character voice / rules | `prompts.py` → `build_system_prompt()` |
| Force reply command | Message containing **`!soppo`** (see `bot.py` → `message_has_trigger`) |

## Extending later

- **Slash commands**: add a `discord.app_commands.CommandTree` in `setup_hook` and sync to a guild or globally.
- **Per-channel behavior**: branch on `message.channel.id` or store settings in a dict / small DB.
- **Stronger “no repeat”**: adjust the `last_bot_reply` block in `prompts.py` or add similarity checks before send.

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `Missing or empty environment variable: DISCORD_BOT_TOKEN` | No `.env` or token not set; fix `.env` next to `main.py`. |
| Bot online but never reads text | **Message Content Intent** not enabled in the portal, or bot lacks **View Channel** / **Read Message History** in `#general`. |
| Bot ignores all messages | Channel is not named like `DISCORD_CHANNEL_NAME` (default `general`), or messages are in a thread / wrong server. |
| `Could not reach Ollama` | Ollama not running, wrong `OLLAMA_URL`, or firewall blocking `localhost:11434`. |
| `model '…' not found` / HTTP 404 | That tag is not installed. Run `ollama pull <OLLAMA_MODEL>` or set `OLLAMA_MODEL` to a name from `ollama list`. |
| Replies too spammy / too quiet | Lower or raise `SPONTANEOUS_REPLY_CHANCE`; increase `REPLY_COOLDOWN_SECONDS`. |
| `!soppo` does nothing | Must appear as its own token (regex word boundary); not inside another word. |

## License

Use and modify for your own projects; no license file is included by default.
