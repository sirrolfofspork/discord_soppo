# SOPPO Discord Changelog

## 2026-06-28 — Channel sleep latch for bot-loop control

### Runtime behavior

- Added explicit sleep phrases such as `Soppo sleep`, `Soppo, go to sleep`, `Sash stand down`, and `!soppo stop replying`.
- Sleep commands mute SOPPO for the current channel and clear all inferred follow-up windows in that channel.
- While asleep, SOPPO ignores all messages in that channel except explicit wake phrases such as `Soppo wake up`, `Sash resume`, or `!soppo wake`.
- Sleep and wake commands do not send Discord replies, so the guard does not add fuel to a bot loop.

### Verification

- `./.venv/bin/python -m unittest tests.test_followup_soft_close -v`
- `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
- `./.venv/bin/python -m unittest discover -v`
- Result: targeted sleep/follow-up suite passed; full 70-test suite passed; compileall passed.

## 2026-06-20 — Newest live message priority hardening

### Runtime behavior

- Marked the final live Discord user message in the outbound LLM prompt as the message to answer directly.
- Deferred neutral summary regeneration on reply-generating turns until after SOPPO sends her reply, preventing the current user message from being folded into a system summary before it is answered.
- Strengthened channel summary and structured-memory prompt wording so memories/summaries are background facts, not live requests or current conversation turns.
- Added an explicit global behavior rule: do not answer memory, summaries, or prior scene notes as if they are live messages.

### Verification

- `./.venv/bin/python -m unittest tests.test_prompts tests.test_channel_memory tests.test_structured_memory tests.test_neutral_context_memory -v`
- `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
- `./.venv/bin/python -m unittest discover -v`
- Result: targeted 31-test suite passed; full 65-test suite passed; compileall passed.

## 2026-06-19 — User systemd service for SOPPO Discord

### Runtime behavior

- Added a user-level `soppo-discord.service` template so SOPPO can be supervised by systemd instead of a fragile terminal/background process.
- Installed and enabled the service on the Hermes host with restart-on-failure behavior.
- Left Discord token handling unchanged: `main.py` still loads secrets from the repo-local `.env`; the unit file contains no credentials.

### Verification

- `./.venv/bin/python -m compileall -q -x '(^|/)(\.venv|\.git)(/|$)' .`
- `systemctl --user enable --now soppo-discord.service`
- `systemctl --user status soppo-discord.service --no-pager`
- `journalctl --user -u soppo-discord.service -n 80 --no-pager`

### Operational note

SOPPO can now reconnect automatically if the Python bot process exits. LM Studio remains a separate dependency when `LLM_BACKEND=lmstudio`; if LM Studio or its loaded model is unavailable, SOPPO may stay online but fail reply generation until the backend is restored.

## 2026-06-18 — Memory handling and observability pass

Commit: `01ca1dd Improve SOPPO memory handling`

### Runtime behavior

- Took SOPPO offline before memory work and left her offline afterward.
- Changed structured memory injection from broad importance/hit-count dumping to relevance-gated retrieval against the newest live user message.
- Tightened channel summary context language so summaries are treated as background continuity only, not active bullets to answer or continue.
- Kept raw transcript injection tiny via the configured recent-turn limit.
- Preserved existing backend routing; no new model/provider path or framework was introduced.

### Neutral summary and memory health

- Added summary deferral/failure observability for:
  - threshold not reached,
  - cooldown active,
  - no pending turns,
  - summary already in progress,
  - generation failure,
  - empty generated summary.
- Added non-content summary health metadata to the existing channel-summary record:
  - `messages_since_regen`,
  - `pending_turn_count`,
  - `last_seen_message_time`,
  - `last_regen_attempt`,
  - `last_regen_status`,
  - `last_regen_error`,
  - `cooldown_remaining_seconds`.
- Explicitly avoided persisting pending raw Discord message content in diagnostic metadata.

### Tooling and documentation

- Added `tools/inspect_memory.py` for offline inspection of `memory_store.json` without Discord credentials or bot startup.
- Added `Kanban.md` to track completed memory work, ready backlog, and guardrails.
- Added this changelog for quick future pickup.
- Updated `.gitignore` to keep runtime logs out of commits.

### Tests and verification

- Added/updated tests for:
  - relevance-gated structured memory retrieval,
  - summary background-context instructions,
  - summary health metadata merge behavior,
  - threshold/cooldown/success metadata states,
  - neutral summary generation behavior,
  - follow-up soft-close behavior.
- Verification run before commit:
  - `./.venv/bin/python -m unittest discover -v`
  - `./.venv/bin/python -m compileall -q -x '(^|/)(\.venv|\.git)(/|$)' .`
  - `./.venv/bin/python tools/inspect_memory.py`
- Result: 64 tests passed, compileall passed, memory inspection succeeded.

### Remaining backlog

See `Kanban.md` for the current pickup list. Near-term candidates:

- Tighten summary topic-boundary representation.
- Add memory pruning/quarantine review mode.
- Add per-user memory retrieval regression tests.
- Add DM memory health tests.
