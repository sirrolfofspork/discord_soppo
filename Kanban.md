# SOPPO Memory Improvements Kanban

## Done

- [x] Take SOPPO Discord offline before memory work.
- [x] Relevance-gate structured memory retrieval against the newest live user message.
- [x] Clarify that channel summaries are background continuity, not bullets to answer.
- [x] Add memory observability.
  - Logs when summary regeneration is deferred because the threshold has not been reached.
  - Logs when summary regeneration is deferred because cooldown is active.
  - Logs when another summary generation is already running.
  - Logs summary LLM timeout/failure without leaking Discord content.
- [x] Persist pending-summary metadata without raw message content.
  - Stores health/debug fields such as messages_since_regen, pending_turn_count, last_seen_message_time, last_regen_attempt, last_regen_status, last_regen_error, and cooldown_remaining_seconds.
  - Does not persist pending raw Discord messages.
- [x] Add local memory inspection tooling.
  - `tools/inspect_memory.py` inspects memory_store.json without Discord credentials or bot startup.
  - Prints namespaces, summaries, structured memories, health metadata, stale/high-hit records, and suspicious identity terms.
- [x] Add user systemd service supervision.
  - `deploy/soppo-discord.service` runs `.venv/bin/python main.py` from the project root.
  - User unit is installed as `~/.config/systemd/user/soppo-discord.service`, enabled, and configured with restart-on-failure.
  - Secrets remain in `.env`; the unit file contains no Discord token or API key.

## Ready

- [ ] Tighten summary topic-boundary representation.
  - Summaries should explicitly mark current topic, previous/closed topics, unresolved questions, and durable facts.
  - Goal: avoid dragging old emotional/contextual residue into fresh messages.

- [ ] Add memory pruning/quarantine review mode.
  - Flag repeated jokes, identity/body contamination, stale relationship claims, and high-hit memories with no recent relevance.
  - Do not auto-delete on first pass; produce review output for SKK/Leva.

- [ ] Add per-user memory retrieval regression tests.
  - Ensure only the current speaker's user-scoped memories are injected.
  - Ensure other users' memories are not exposed or used.

- [ ] Add DM memory health tests.
  - Verify DM summary namespaces and metadata behavior.
  - Verify deferred summary state when fewer than the threshold number of DM turns exist.

## Guardrails

- Change history lives in `CHANGELOG.md`; update it after substantive SOPPO behavior/memory changes.
- Repo-local handoff locations are listed in `AGENTS.md` under "Documentation Map".
- Keep SOPPO offline during invasive memory edits unless SKK explicitly asks for restart.
- Preserve existing backend routing; do not add a new model/provider path for memory maintenance.
- Keep raw transcript injection tiny: only the configured recent turns.
- Do not store raw Discord message content in health metadata.
- Prefer tests and observability before more personality/prompt surgery.
