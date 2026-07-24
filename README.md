# SOPPO Discord Bot

SOPPO is a Discord chatbot that role-plays as **M4 SOPMOD II** (*Girls' Frontline*). It listens in configured channels, builds a layered prompt (persona, speaker profile, lore, channel summary, structured memories, recent chat), calls a configurable LLM backend, and posts replies in character.

This repository is intended to run on a Linux host (for example the Hermes machine) with a local LLM backend, optional OpenAI for clerical memory work, and optional user-level systemd supervision.

## Documentation map

| Document | Audience | Contents |
|----------|----------|----------|
| [README.md](README.md) (this file) | Everyone | Overview, setup, configuration summary, run/test commands |
| [docs/USER_MANUAL.md](docs/USER_MANUAL.md) | Operators | Day-to-day Discord behavior, systemd control, memory review workflows |
| [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) | Contributors | Repo layout, architecture boundaries, testing, change workflow |
| [docs/soppo_soul.md](docs/soppo_soul.md) | Character authors | Persona runtime anchor and identity boundaries |
| [AGENTS.md](AGENTS.md) | AI agents / maintainers | Operating rules and guardrails |
| [CHANGELOG.md](CHANGELOG.md) | Maintainers | What changed and how it was verified |
| [Kanban.md](Kanban.md) | Maintainers | Memory-improvement backlog and guardrails |

## Features

- **Discord integration**: Channel ID filter (preferred) or channel-name fallback; ignores self; optional controlled replies to other bots.
- **Response triggers**: Mentions, reply chains, `!soppo`, configured name aliases (`BOT_NAME_ALIASES`), inferred follow-up window, rare spontaneous replies with cooldown.
- **Channel sleep/wake**: Per-channel mute without bot replies (`Soppo sleep`, `Sash stand down`, `!soppo stop replying`, and similar).
- **LLM backends** (switch via `.env`, not code changes): Ollama, LM Studio (OpenAI-compatible local server), OpenAI API.
- **Layered memory**: Tiny raw transcript, neutral channel summaries, structured long-term memories in `memory_store.json`, optional API memory review queue.
- **Curated context**: Per-user profiles (`user_profiles.json`), GFL lore snippets (`lore_store.json`), persona in `prompts.py`.
- **Safety defaults**: Strips risky mass pings from model output; `allowed_mentions` disables `@everyone` / `@here` on sends.

## Architecture (high level)

```text
main.py          → load .env, load_config(), start bot
bot.py           → Discord events, should-respond logic, prompt assembly, reply coalescing
config.py        → Environment loading and validation
prompts.py       → SOPPO/Sash persona and prompt formatting
llm_client.py    → Routes live replies to Ollama or OpenAI-compatible APIs
ollama_client.py → Ollama /api/chat
openai_client.py → OpenAI API and LM Studio local server
lore.py          → Keyword lore matching from lore_store.json
user_profiles.py → Load user_profiles.json at startup
memory.py        → Channel summary helpers and neutral-summary prompt blocks
memory_store.py  → JSON namespace/key store (flock-locked, merge-safe writes)
memory_extractor.py → Deterministic structured-memory extraction and retrieval
memory_reviewer.py  → Optional API-backed memory candidate review
tools/*          → Offline memory inspection, import, review, pruning scan
```

Prompt layers (conceptual order):

1. Stable persona (`prompts.py`)
2. Current speaker profile (if present in `user_profiles.json`)
3. Relevant lore (alias match on current/recent text)
4. Channel neutral summary + structured memories (background only, not live requests)
5. Small raw recent transcript
6. Newest live user message (explicitly marked as the message to answer)

Live SOPPO replies use `LLM_BACKEND`. Neutral summaries and optional memory review can use separate clerical backends (`SUMMARY_LLM_BACKEND`, `MEMORY_REVIEW_*`).

## Requirements

- **Python 3.11+**
- A **Discord bot** application and token ([Discord Developer Portal](https://discord.com/developers/applications))
- One configured LLM backend: **Ollama**, **LM Studio**, or **OpenAI API**
- For LM Studio: local OpenAI-compatible server running with a loaded model

## Setup

### 1. Clone and enter the repo

```bash
cd /path/to/soppo_discord
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`. Minimum required values:

- `DISCORD_BOT_TOKEN` — from the Discord Developer Portal
- `LLM_BACKEND` — `ollama`, `lmstudio`, or `openai`
- Backend-specific settings (see [Configuration](#configuration))

Optional JSON files (not committed; create locally as needed):

- `user_profiles.json` — per-Discord-user background for prompt injection; private and gitignored. Use `docs/user_profiles_template.json` as the public example/schema.
- `lore_store.json` — curated GFL lore entries (sample entries may ship in repo)
- `memory_store.json` — created at runtime; holds summaries and structured memories

### 4. Discord bot settings

In the Developer Portal, under **Bot**:

- Enable **Privileged Gateway Intents** → **Message Content Intent** (required)

Invite the bot with permissions to **Read Messages**, **Send Messages**, and **Read Message History** in target channels.

### 5. LLM backend

**Ollama** — ensure the daemon is running and the model is pulled:

```bash
ollama pull qwen3.5:4b
```

**LM Studio** — start the local OpenAI-compatible server, load a model, then set `LMSTUDIO_BASE_URL` and `LMSTUDIO_MODEL` to match.

**OpenAI** — set `OPENAI_API_KEY` and `OPENAI_MODEL`.

## Configuration

Copy `.env.example` to `.env`. Variable names match `config.py` and are documented at the bottom of that file.

### Discord and behavior

| Variable | Purpose |
|----------|---------|
| `DISCORD_BOT_TOKEN` | Required bot token |
| `DISCORD_ALLOWED_CHANNEL_IDS` | Comma-separated channel IDs; **preferred** when set |
| `DISCORD_CHANNEL_NAME` | Name fallback when IDs unset (default `general`) |
| `BOT_NAME_ALIASES` | Comma-separated names that count as addressing SOPPO (e.g. `SOPPO,Sash,M4`) |
| `RESPOND_TO_OTHER_BOTS` | `false` by default |
| `BOT_AUTHOR_COOLDOWN_SECONDS` | Loop guard after replying to another bot |
| `SPONTANEOUS_REPLY_CHANCE` | 0.0–1.0 (default `0.10`) |
| `REPLY_COOLDOWN_SECONDS` | Cooldown after any reply before spontaneous replies |
| `INFERRED_FOLLOWUP_WINDOW_SECONDS` | Sliding window for follow-up without re-mention (default 180) |

### Live LLM backend

| Variable | Purpose |
|----------|---------|
| `LLM_BACKEND` | `ollama` \| `lmstudio` \| `openai` |
| `OLLAMA_URL`, `OLLAMA_MODEL` | Ollama settings |
| `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL`, `LMSTUDIO_API_KEY` | LM Studio settings |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS` | OpenAI settings |
| `OLLAMA_TEMPERATURE`, `OLLAMA_TOP_P`, `OLLAMA_MAX_TOKENS` | Sampling (used where supported) |

### Memory and context

| Variable | Purpose |
|----------|---------|
| `MAX_CONTEXT_MESSAGES` | Rolling unsummarized history cap per channel |
| `MAX_CONTEXT_MESSAGES_BEFORE_SUMMARY` | Legacy rollover threshold (compatibility/tests) |
| `SUMMARY_BATCH_SIZE` | Turns folded per legacy rollover |
| `MAX_CHANNEL_SUMMARY_CHARS` | Legacy summary size cap |
| `MEMORY_STORE_PATH` | Path to JSON memory store (default `memory_store.json`) |
| `MAX_PROMPT_CHARS` | Total context character safety valve |
| `RECENT_RAW_TURNS` | Raw transcript turns after summary (default 3; set in code env, not in `.env.example`) |
| `SUMMARY_REGEN_MESSAGE_COUNT` | Messages before neutral summary regen (default 10) |
| `SUMMARY_REGEN_MIN_SECONDS` | Cooldown between neutral summary regens (default 300) |
| `MAX_NEUTRAL_SUMMARY_CHARS` | Neutral summary size cap (default 1800) |
| `RESERVED_GLOBAL_MEMORY_SLOTS` | High-value global memories without lexical overlap (0–5, default 2) |

### Clerical / API memory (optional)

| Variable | Purpose |
|----------|---------|
| `SUMMARY_LLM_BACKEND` | `reply` (default), `ollama`, `openai`, or `lmstudio` for neutral summaries |
| `SUMMARY_OPENAI_*` | Optional separate OpenAI settings for summaries |
| `MEMORY_REVIEW_ENABLED` | `true` to propose memory candidates after summary regen |
| `MEMORY_REVIEW_LLM_BACKEND` | Backend for review (typically `openai`) |
| `MEMORY_REVIEW_OPENAI_*` | Optional separate OpenAI settings for review |
| `MEMORY_REVIEW_QUEUE_PATH` | JSONL queue path (default `memory_review_queue.jsonl`) |

When `SUMMARY_LLM_BACKEND=openai` or memory review uses OpenAI, an API key must be available via the dedicated `*_OPENAI_API_KEY` vars or `OPENAI_API_KEY`.

### Reply shaping

| Variable | Purpose |
|----------|---------|
| `DISCORD_REPLY_SOFT_LIMIT` | Target max length before trimming (default 500) |
| `DISCORD_REPLY_HARD_LIMIT` | Max chars per Discord message chunk (default 1800) |

See [docs/USER_MANUAL.md](docs/USER_MANUAL.md) for operator-facing behavior details and [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) for memory namespace layout.

## Running the bot

### Foreground (development)

```bash
source .venv/bin/activate
python main.py
```

Startup logs include bot user/id, guilds, channel filter mode, spontaneous reply settings, and summary thresholds.

### User systemd service (production)

Template: `deploy/soppo-discord.service`. Adjust `WorkingDirectory` and `ExecStart` paths if the repo is not at the default Hermes location.

```bash
mkdir -p ~/.config/systemd/user
cp deploy/soppo-discord.service ~/.config/systemd/user/soppo-discord.service
# Edit paths in the unit file if needed
systemctl --user daemon-reload
systemctl --user enable --now soppo-discord.service
```

Common commands:

```bash
systemctl --user status soppo-discord.service --no-pager
journalctl --user -u soppo-discord.service -f
systemctl --user restart soppo-discord.service
systemctl --user stop soppo-discord.service
```

Secrets stay in repo-local `.env` (loaded by `main.py` via `python-dotenv`). Do not put tokens in the unit file.

**Note:** If `LLM_BACKEND=lmstudio`, LM Studio must be running separately. The bot may stay online while the LLM is down, but replies will fail until the backend is restored.

## Testing

Tests use the standard library `unittest` runner (no pytest config in this repo).

```bash
./.venv/bin/python -m unittest discover -v
```

Targeted suites (examples):

```bash
./.venv/bin/python -m unittest tests.test_structured_memory tests.test_channel_memory -v
./.venv/bin/python -m unittest tests.test_prompts tests.test_followup_soft_close -v
```

After code changes:

```bash
./.venv/bin/python -m compileall -q -x '(^|/)(\.venv|\.git)(/|$)' .
```

As of 2026-07-07, the full suite is **127 tests** (see [CHANGELOG.md](CHANGELOG.md) for current verification notes).

## Memory tools (offline)

These tools read or write local JSON only. They do not start Discord or call an LLM unless noted.

| Tool | Purpose |
|------|---------|
| `tools/inspect_memory.py` | Inspect summaries, structured memories, health metadata |
| `tools/review_memory_pruning.py` | Review-only scan for pruning candidates (no store mutation) |
| `tools/import_memory_candidates.py` | Convert curated JSONL into review-queue items |
| `tools/process_memory_review_queue.py` | Summarize queue; apply human-`approved` items |
| `tools/serve_memory_review.py` | Local browser UI to approve/reject pending queue items |
| `review_soppo_memory.sh` | Wrapper around queue summary + apply-approved |

Quick inspect:

```bash
./.venv/bin/python tools/inspect_memory.py
./.venv/bin/python tools/inspect_memory.py /path/to/memory_store.json
```

Memory review workflow is documented in [docs/USER_MANUAL.md](docs/USER_MANUAL.md).

Local web review UI:

```bash
./.venv/bin/python tools/serve_memory_review.py
# open http://127.0.0.1:8765/
```

Phone/home-network access:

```bash
./.venv/bin/python tools/serve_memory_review.py --lan
# open the printed http://192.168.x.x:8765/ URL from your phone
```

LAN mode binds to all interfaces and has no login page, so use it only on a trusted home network and stop it when finished.

**Guardrail:** `process_memory_review_queue.py --apply-approved` normally refuses to run while `soppo-discord.service` is active. Use `--hot` to apply approved memories without restarting SOPPO; the running bot refreshes `memory_store.json` from disk before the next structured-memory retrieval. Use `--force` only as a deliberate override.

## Safety and secrets

**Never commit:**

- `.env`, Discord tokens, API keys, OAuth tokens
- `memory_store.json`, `memory_review_queue.jsonl`, `user_profiles.json`, user-profile backups (gitignored; may contain private chat-derived content)
- `*.log`, `logs/`, `gittoken.txt`

`.gitignore` already excludes these paths. Treat runtime logs and memory stores as sensitive if they contain Discord content.

Edit `user_profiles.json` and restart the bot to refresh in-memory profiles. Lore and persona changes require editing `lore_store.json` or `prompts.py` respectively, then restart.

## Troubleshooting

| Symptom | Likely cause |
|---------|----------------|
| `Missing or empty environment variable: DISCORD_BOT_TOKEN` | No `.env` or empty token |
| Bot online but never reads text | Message Content Intent disabled, or missing channel permissions |
| Bot ignores all messages | Channel not in `DISCORD_ALLOWED_CHANNEL_IDS`, or name mismatch when using fallback |
| Bot ignores another bot | `RESPOND_TO_OTHER_BOTS=false` (default) |
| `Could not reach Ollama` | Ollama not running or wrong `OLLAMA_URL` |
| LM Studio connection errors | Local server not running, wrong base URL, or no model loaded |
| `model '…' not found` | Pull/install model or fix `OLLAMA_MODEL` / `LMSTUDIO_MODEL` |
| Replies too spammy / too quiet | Adjust `SPONTANEOUS_REPLY_CHANCE` and `REPLY_COOLDOWN_SECONDS` |
| `!soppo` does nothing | Must be its own token (word boundary), not embedded in another word |
| Slow LLM causes stale replies | Reply coalescing keeps one pending message per channel; see [CHANGELOG.md](CHANGELOG.md) |
| Memory apply refused while bot runs | Use review UI **Hot-apply while SOPPO is running** or CLI `--hot`; use `--force` only as deliberate override |
| Identity confusion after roleplay | Identity-reset probes purge contaminated context; see `docs/soppo_soul.md` |

For operational procedures (sleep/wake, memory import, service control), see [docs/USER_MANUAL.md](docs/USER_MANUAL.md).

## License

Use and modify for your own projects; no license file is included by default.
