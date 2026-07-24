# SOPPO Operator Manual

This guide is for day-to-day operation of the SOPPO Discord bot: how she behaves in channels, how to control the service, and how to review or import long-term memory without touching live Discord state unnecessarily.

For installation and environment variables, see [README.md](../README.md). For code architecture, see [DEVELOPER_GUIDE.md](DEVELOPER_GUIDE.md).

## What SOPPO does in Discord

SOPPO (also called Sash in some prompts) listens in configured channels, decides whether to reply, assembles context, calls the configured LLM, and posts an in-character response.

She **does not**:

- Greet users when they come online (no presence-based greetings)
- Send `@everyone` or `@here`
- Reply to herself
- Reply in channels outside the configured filter (unless you broaden the config)

By default she **ignores other Discord bots**. Humans are unaffected by bot-author cooldown logic.

## Channel scope

Two modes (configured in `.env`):

1. **Channel IDs (preferred):** `DISCORD_ALLOWED_CHANNEL_IDS=123...,456...` — only those channels receive processing.
2. **Name fallback:** When IDs are empty, only channels whose name matches `DISCORD_CHANNEL_NAME` (default `general`, case-insensitive).

Use channel IDs when the bot is in multiple servers. A name fallback can accidentally match every server's `#general`.

## When SOPPO replies

### Always (direct address)

SOPPO replies when any of these are true:

- Someone **@mentions** the bot
- Someone **replies** to one of the bot's messages
- The message contains **`!soppo`** as its own word/token
- The message contains a configured **name alias** (`BOT_NAME_ALIASES`, e.g. `SOPPO`, `Sash`, `M4`)

### Sometimes (inferred follow-up)

After you address SOPPO directly, a **sliding window** (`INFERRED_FOLLOWUP_WINDOW_SECONDS`, default 180 seconds) lets the same user continue talking without re-mentioning her, unless the message looks like ambient chatter or a side thread (reply to someone else, @mention only other users).

### Rarely (spontaneous)

When not directly addressed and not in an inferred follow-up, SOPPO may reply at random with probability `SPONTANEOUS_REPLY_CHANCE` (default 0.10), subject to `REPLY_COOLDOWN_SECONDS` after any prior reply.

### Reply coalescing (slow LLM)

If the LLM is slow, SOPPO keeps **one active reply per channel**. While generating, newer messages can replace the pending one by priority:

1. Identity reset probes
2. Direct address (mention, reply, trigger, alias)
3. Inferred follow-up
4. Spontaneous / ambient (ignored while busy)

This prevents a backlog of stale ghost replies.

## Sleep and wake (per channel)

Sleep commands **mute SOPPO in the current channel only**. They do **not** send a Discord reply (avoids bot loops).

**Sleep examples** (must match the short-command patterns in `bot.py`):

- `Soppo sleep`
- `Soppo, go to sleep`
- `Sash stand down`
- `!soppo stop replying`
- `Sash, stop talking`

**Wake examples:**

- `Soppo wake up`
- `Sash resume`
- `!soppo wake`

While asleep, all messages in that channel are ignored except explicit wake phrases. Sleep also clears inferred follow-up state and pending replies for that channel.

Sleep state is **in-memory only** — restarting the bot clears channel sleep latches.

## Soft close (conversation end)

Short phrases like "that's all", "we're good", or "stand down" (without full sleep syntax) can end inferred follow-up windows. See `tests/test_followup_soft_close.py` for accepted patterns.

## Identity checks

Direct identity probes (`who are you?`, `are you Leva?`, `identity check`, etc.) trigger **context cleanup** before the LLM reply:

- Recent raw history, pending summary turns, and rolling channel summary for that channel are purged
- The model answers from core persona, speaker profile, identity-reset context, and the newest live message only

SOPPO may respond with a snap-back line: *"I'm Sash. I got tangled in the scene. Resetting orientation."*

Persona and identity rules live in `prompts.py` and [soppo_soul.md](soppo_soul.md).

## Memory from an operator's perspective

SOPPO does **not** rely on the LLM to permanently remember facts. Memory is app-managed:

| Layer | Where it lives | Operator action |
|-------|----------------|-----------------|
| Persona | `prompts.py`, `docs/soppo_soul.md` | Edit and restart bot |
| Speaker profile | `user_profiles.json` | Edit and restart bot |
| Lore snippets | `lore_store.json` | Edit and restart bot |
| Channel summary | `memory_store.json` | Auto-generated; inspect with tools |
| Structured memories | `memory_store.json` | Auto-extracted, API-reviewed, or imported |

Summaries and structured memories are injected as **background context only**. They must not be treated as live user requests (the bot prompt enforces this).

### Inspecting memory (safe, offline)

From the repo root:

```bash
./.venv/bin/python tools/inspect_memory.py
```

Shows namespaces, channel/DM summaries (including section headings when present), structured memory records, health metadata, stale/high-hit records, and suspicious identity terms. Does not connect to Discord.

Pruning review (read-only flags, no writes):

```bash
./.venv/bin/python tools/review_memory_pruning.py
./.venv/bin/python tools/review_memory_pruning.py --json
```

### API memory review queue

When `MEMORY_REVIEW_ENABLED=true`, after neutral summary regeneration the API may propose memory candidates. Local validation:

- Applies safe, non-conflicting candidates directly to `memory_store.json`
- Queues conflicts, risky, or profile-overlapping items in `memory_review_queue.jsonl`

**Human review workflow:**

1. **Web UI (recommended for pending items):**

   ```bash
   ./.venv/bin/python tools/serve_memory_review.py
   ```

   Open `http://127.0.0.1:8765/` in a browser. The page lists **pending** queue entries by default with Approve/Reject controls, then offers **Apply approved memories** (same guardrails as the CLI). Use **Show all queue entries** to inspect approved, rejected, or applied rows.

   To review from a phone on the home network:

   ```bash
   ./.venv/bin/python tools/serve_memory_review.py --lan
   ```

   Open the printed `http://192.168.x.x:8765/` URL from the phone. LAN mode binds to all interfaces and has no login page, so use it only on a trusted network and stop it when finished.

   Optional flags: `--host`, `--port`, `--lan`, `--queue`, `--memory-store`.

2. Summarize pending items (CLI):

   ```bash
   ./review_soppo_memory.sh
   ```

   Or manually:

   ```bash
   ./.venv/bin/python tools/process_memory_review_queue.py --summary
   ```

3. **Manual JSONL edit** (alternative to the web UI). Change wanted items:

   ```json
   "status": "pending"
   ```

   to:

   ```json
   "status": "approved"
   ```

   Use `"status": "rejected"` to discard.

4. Apply approved items (prefer bot **stopped**):

   ```bash
   systemctl --user stop soppo-discord.service   # recommended
   ./review_soppo_memory.sh
   ```

   Or from the web UI: **Apply approved memories**. If SOPPO is running, check **Hot-apply while SOPPO is running** to apply without restarting; the bot reloads `memory_store.json` from disk before the next structured-memory retrieval. The unchecked apply path still refuses while `soppo-discord.service` is active. CLI equivalent:

   ```bash
   ./.venv/bin/python tools/process_memory_review_queue.py --apply-approved --hot --summary
   ```

### Curated memory import

To bulk-import human-curated memories without writing directly to the store:

```bash
./.venv/bin/python tools/import_memory_candidates.py your_curated_rows.jsonl \
  --output memory_review_queue.jsonl \
  --dry-run

./.venv/bin/python tools/import_memory_candidates.py your_curated_rows.jsonl \
  --output memory_review_queue.jsonl
```

Then follow the review-queue workflow above. Import never writes directly to `memory_store.json`.

Expected curated row fields include `id`, `category`, `memory_text`, and optional evidence/scores (see `tools/import_memory_candidates.py` and `tests/test_import_memory_candidates.py`).

## Service control (systemd user unit)

If installed per [README.md](../README.md):

| Action | Command |
|--------|---------|
| Status | `systemctl --user status soppo-discord.service --no-pager` |
| Follow logs | `journalctl --user -u soppo-discord.service -f` |
| Restart | `systemctl --user restart soppo-discord.service` |
| Stop | `systemctl --user stop soppo-discord.service` |
| Start | `systemctl --user start soppo-discord.service` |

The unit runs `.venv/bin/python main.py` from the project root. Secrets are loaded from `.env` only.

**When to stop the bot:**

- Before invasive manual edits to `memory_store.json`
- Before applying approved memory queue items (unless you intentionally use `--force`)
- During memory-system development (see [Kanban.md](../Kanban.md) guardrails)

**Dependencies:**

- `LLM_BACKEND=ollama` → Ollama daemon must be running
- `LLM_BACKEND=lmstudio` → LM Studio local server + loaded model
- `LLM_BACKEND=openai` → valid `OPENAI_API_KEY`
- Optional summary/review OpenAI backends → separate or shared API keys as configured

## User profiles and lore

**User profiles** (`user_profiles.json`, gitignored):

- Keys are Discord user ID strings
- Only the **current speaker's** profile is injected
- Restart the bot after edits

**Lore** (`lore_store.json`):

- Short curated entries with aliases, factual summary, and optional in-character take
- Matched by aliases in the current message (and related retrieval logic)
- Author/review lore content by hand; do not auto-generate large canon dumps

## Common commands cheat sheet

```bash
# Run in foreground
./.venv/bin/python main.py

# Full test suite
./.venv/bin/python -m unittest discover -v

# Inspect memory store
./.venv/bin/python tools/inspect_memory.py

# Memory review queue summary + apply approved
./review_soppo_memory.sh

# Service logs
journalctl --user -u soppo-discord.service -n 100 --no-pager
```

## Privacy notes

- `memory_store.json` may contain chat-derived summaries and durable facts from Discord
- `memory_review_queue.jsonl` may contain proposed memory text awaiting review
- Runtime logs in journald or `logs/` may contain operational metadata; treat as sensitive if Discord content appears

Do not commit these files. See [README.md](../README.md#safety-and-secrets).

## Uncertainties / not implemented here

- **Slash commands:** Not present in the current codebase; triggers are message-based.
- **llama.cpp server:** Mentioned as a future option in [AGENTS.md](../AGENTS.md); no dedicated client module yet (LM Studio uses the OpenAI-compatible path).
- **Persistent sleep state:** Channel sleep is not persisted to disk across restarts.
- **Web UI for memory review:** Queue review is JSONL file editing plus CLI tools.

If behavior differs from this document, trust the code and [CHANGELOG.md](../CHANGELOG.md), then update the docs.
