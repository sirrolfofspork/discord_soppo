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
- [x] Harden newest-live-message priority.
  - Outbound prompts mark the final live Discord user message explicitly.
  - Neutral summary regeneration is deferred until after SOPPO replies, so the current user turn is not folded into a system summary before it is answered.
  - Channel summaries and structured memories now say they are background only, not live requests or current conversation turns.

- [x] Add channel sleep latch for bot-loop control.
  - `Soppo sleep`, `Sash stand down`, and `!soppo stop replying` mute SOPPO in the current channel without sending a reply.
  - `Soppo wake up`, `Sash resume`, and `!soppo wake` unmute the channel without sending a reply.
  - Entering sleep clears all inferred follow-up windows for that channel.

- [x] Add identity contamination snap-back hardening.
  - Main prompt says Sash/SOPPO never becomes copied roleplay, quoted dialogue, third-party characters, or temporary scene participants.
  - Identity checks trigger a snap-back protocol: `I'm Sash. I got tangled in the scene. Resetting orientation.`
  - Neutral summaries and structured-memory extraction reject temporary roleplay facts as permanent identity/personality memory unless explicitly durable.

- [x] Add identity-confrontation context cleanup.
  - Direct identity probes such as `who are you?`, `are you Leva?`, and `what's the deal with Leva?` purge recent raw history, pending summary turns, previous bot-reply reminders, and rolling channel summary before the reply.
  - The LLM remains in the loop, answering only from the core identity prompt, current speaker profile, identity-reset context, and newest live message.
  - Current-speaker profile fields now include username/pronouns while explicitly warning SOPPO not to adopt the speaker's identity.
  - Leva is represented as separate from SOPPO and as an older-sister figure when the current speaker profile is Leva.

- [x] Add reply coalescing for slow LLM backlog control.
  - One active reply per channel; while active, SOPPO keeps only one latest useful pending message for that channel.
  - Priority: identity reset > direct address/mention/reply/trigger/name alias > inferred follow-up > spontaneous/ambient ignored.
  - Newer equal-priority messages replace older ones, and direct `Sash`/`Soppo` messages outrank inferred follow-ups.
  - Sleep commands clear pending replies for that channel.

- [x] Add API-backed memory review queue.
  - Optional `SUMMARY_LLM_BACKEND=openai` lets neutral summaries use API while live SOPPO replies remain local.
  - Optional `MEMORY_REVIEW_ENABLED=true` asks the API to propose memory candidates after summary regeneration.
  - Local validation checks candidate schema, confidence, identity/roleplay risk, existing `memory_store.json`, and ignored `user_profiles.json` before writing.
  - Safe candidates apply automatically; conflicts/risky/profile-overlap candidates append to ignored `memory_review_queue.jsonl`.
  - `tools/process_memory_review_queue.py` summarizes pending items and applies entries manually marked `approved`.

- [x] Phase 1 memory store write safety and observability.
  - `memory_store.json` saves are merge-safe and flock-locked so summary metadata writes do not erase externally added `soppo/global/memories` or `discord/user/.../memories`.
  - `PersistentChannelSummaryMemory.reload_from_disk()` refreshes in-memory state before structured retrieval.
  - Bot logs structured-memory injection count plus type/key/hash metadata without raw Discord or memory text.
  - `tools/process_memory_review_queue.py --apply-approved` refuses when `soppo-discord.service` is active unless `--force` is supplied.

- [x] Phase 1+ curated JSONL import converter.
  - `tools/import_memory_candidates.py` converts curated import JSONL into pending `memory_review_queue.jsonl` items for manual review/apply.
  - Maps `memory_text` → candidate text, category → conservative candidate type, preserves source audit metadata, and uses stable dedup-safe item IDs.
  - Refuses to overwrite existing output unless `--force`; never writes directly to `memory_store.json`.

- [x] Phase 2 reserved global memory retrieval.
  - Configurable `RESERVED_GLOBAL_MEMORY_SLOTS` (default 2, clamped 0–5) injects a bounded set of high-value global identity/canon memories without lexical overlap.
  - Lexical relevance gating remains for user/guild/channel memories and normal global overflow.
  - Scoped memories fill first; reserved globals only use remaining slots up to the configured cap.
  - Structured-memory logs include non-content `selection` metadata (`lexical` vs `reserved_global`).

- [x] Tighten summary topic-boundary representation.
  - Neutral summarizer prompt requires stable section headings: current topic, previous/closed topics, unresolved questions, and durable facts.
  - Channel summary blocks annotate section boundaries and mark closed topics as background only.
  - Legacy unsectioned summaries remain acceptable.

## Ready

- [x] Add memory pruning/quarantine review mode.
  - `tools/review_memory_pruning.py` flags duplicate/near-duplicate records, identity/body contamination, stale relationship claims, high-hit generic/over-trigger records, and scene/joke residue in durable facts.
  - Review-only output for SKK/Leva; no auto-delete or store mutation.

- [x] Add per-user memory retrieval regression tests.
  - Ensure only the current speaker's user-scoped memories are injected.
  - Ensure other users' memories are not exposed or used.
  - Dedicated coverage added via `PerUserMemoryRetrievalBoundaryTests` in `tests/test_structured_memory.py`.

- [x] Add DM memory health tests.
  - Verify DM summary namespaces and metadata behavior.
  - Verify deferred summary state when fewer than the threshold number of DM turns exist.
  - Verify intentional bounded cross-channel structured-memory retrieval in DMs (not strict DM isolation): relevant guild/channel friend memories may surface; other users' user-scoped memories must not.

## Future / Ideas from Little Lantern review

- [ ] Add memory operation receipts.
  - Persist compact per-channel/per-DM receipts for memory actions such as applied, queued, dropped, duplicate, or updated.
  - Include non-content metadata where possible: timestamp, action, type, scope, hash/key, source, and reason code.
  - Inject a short receipt block so SOPPO knows whether a fact was actually remembered, only queued for review, or rejected as duplicate/risky.
  - Add tests that queued or dropped candidates are not treated as durable remembered facts.

- [ ] Add vision-safe memory provenance before enabling Discord vision.
  - Extend structured memory records with explicit provenance fields such as `source`, `confidence`, `requires_review`, and `evidence_ref` / Discord message reference.
  - Treat image-derived observations as candidates by default, not canon or high-confidence durable facts.
  - Distinguish user-explicit statements from inferred visual observations in retrieval and prompt wording.

- [ ] Add alias/retrieval-term enrichment for near-duplicate memories.
  - When a near-duplicate structured memory is detected, update hits/timestamps and merge high-signal aliases or retrieval terms instead of creating another record.
  - Keep canonical memory text stable unless a human-approved review flow rewrites it.
  - Add tests proving aliases improve lexical recall without broadening retrieval into unrelated channels/users.

- [ ] Add an operator-authored canon/behaviour memory layer.
  - Create a clearly separate namespace for SKK/Leva-authored rules or canon, distinct from API-extracted memories.
  - Ensure automated memory review cannot create or modify binding behaviour/canon entries.
  - Retrieve this layer only through explicit triggers or tightly bounded reserved slots, and inject it as operator-authored context.

- [ ] Add a bounded quiet maintenance pass.
  - After a channel is quiet, run at most one background maintenance job to refresh neutral summaries, propose memory candidates, and record receipts without sending a Discord reply.
  - Reuse existing generation locks / summary-in-progress guards so maintenance does not pile up behind live replies.
  - Keep logs privacy-safe: hashes, counts, reason codes, and status only unless explicitly running an operator review tool.

- [ ] Improve memory review classification by destination.
  - Extend pruning/review tooling to classify candidates as keep structured memory, move to summary, move to operator canon, move to user profile, discard routine chatter, discard roleplay residue, or queue for SKK.
  - Surface classification reason codes in JSON/text review output.
  - Preserve the current review-only posture: no automatic deletion or quarantine without explicit approval.

## Guardrails

- Change history lives in `CHANGELOG.md`; update it after substantive SOPPO behavior/memory changes.
- Repo-local handoff locations are listed in `AGENTS.md` under "Documentation Map".
- Keep SOPPO offline during invasive memory edits unless SKK explicitly asks for restart.
- Preserve live SOPPO reply backend routing; background summary/memory-review backends may use separate clerical API settings.
- Keep raw transcript injection tiny: only the configured recent turns.
- Do not store raw Discord message content in health metadata.
- Prefer tests and observability before more personality/prompt surgery.
