# SOPPO Discord Changelog

## 2026-08-17 — Sash Presence Engine planning roadmap

- Added a planning-only Kanban roadmap for emotional state, bounded proactive DMs, reference-consistent selfies, and a direct mobile presence app.
- Split the concept into small dependency-ordered cards with deliverables, acceptance criteria, non-goals, and cross-epic release gates.
- Kept every new card in backlog state; no implementation was authorized, no runtime files changed, and `soppo-discord.service` was not touched.

## 2026-08-17 — Memory proposal duplicate suppression

- Added a local pre-write duplicate gate for API-proposed memories against same-namespace review history.
- Pending, approved, applied, and rejected queue entries now suppress exact normalized repeats and conservative high-overlap near-duplicates.
- Added same-batch duplicate suppression while preserving namespace isolation and existing active-store duplicate handling.
- Kept `soppo-discord.service` running; this static code change takes effect on its next restart.
- Verification: `MemoryReviewerTests` ran 9 tests and the full suite ran 175 tests — all passed; compileall and `git diff --check` passed.

## 2026-08-12 — Convert live persona from SOPPO to Sash

- Converted the active `prompts.py` identity from M4 SOPMOD II/SOPPO to Sash, a robotic AI from the future.
- Updated current-facing prompt tests, operator/developer documentation, and the persona runtime anchor.
- Retained legacy repository, systemd service, command aliases, and internal class names for compatibility.
- Normalized the edited prompt file back to LF line endings.
- Kept `soppo-discord.service` offline during the change.

## 2026-08-06 — Coalesced reply and transcript hardening Phase 2

### Runtime behavior

- Replaced queued live `discord.Message` retention with frozen scalar snapshots containing content, author metadata, channel/guild/message IDs, trigger reason, identity-reset state, priority, and reply/reference metadata.
- Coalesced drains now resolve their send channel by captured ID while using only snapshotted trigger data, so later mutation of Discord message, author, channel, guild, or reference objects cannot change delayed work.
- Named and retained coalesced drain tasks, observed task failures, and removed tasks deterministically after completion.
- Added shutdown state that blocks new drains, clears pending/active reply bookkeeping, cancels and awaits retained drains, and always invokes Discord client close from `run_bot()`.
- Replaced ambiguous `[display]: content` user-turn formatting with compact JSON envelopes using `ensure_ascii=False`, keeping adversarial role labels/newlines as data while preserving international text and emoji.
- Sanitized control and structural bracket characters from prompt-facing Discord display names while preserving ordinary punctuation, combining marks, international scripts, and ZWJ emoji sequences.
- Updated structured-memory extraction to parse the new envelope while retaining compatibility with stored legacy `[Display]: message` and `[Display|id]: message` turns.

### Verification

- `./.venv/bin/python -m unittest tests.test_prompts tests.test_structured_memory tests.test_reply_request_phase1 tests.test_neutral_context_memory tests.test_followup_soft_close tests.test_openai_client tests.test_field_regressions -v`
- Result: `Ran 102 tests` — `OK`.
- `./.venv/bin/python -m unittest discover -v`
- Result: `Ran 170 tests` — `OK`.
- `./.venv/bin/python -m compileall -q -x '(^|/)(\.venv|\.git)(/|$)' .`
- Result: compileall passed.
- `git diff --check`
- Result: clean.
- Independent `codex exec review --uncommitted --ephemeral` found no discrete correctness issues.
- SOPPO remained offline throughout implementation and verification; no service or runtime-memory files were changed.

### Runtime validation

- Started a temporary supervised Discord process with process-only overrides `SPONTANEOUS_REPLY_CHANCE=0` and `REPLY_COOLDOWN_SECONDS=0`; `.env` and both inactive systemd units were unchanged.
- Sent one long direct request followed by two direct marker requests while generation was active. Logs recorded two coalesced pending replies, one drain, and only the latest marker request was generated after the active reply; the superseded middle marker received no response.
- Sent hostile multiline text containing counterfeit bracketed assistant/system labels. The visible response matched the requested safe marker, and the LM Studio request retained 4 system + 2 user + 1 assistant roles with the hostile line breaks escaped inside the newest JSON user envelope.
- Delivered SIGINT while the process held an active `ESTABLISHED` connection to LM Studio. The process exited, all Discord and LM Studio client sockets disappeared, LM Studio returned to 138 FDs, and port 1234 retained only its listener plus normal `TIME_WAIT`.
- Resource cleanup passed; the pre-existing top-level `KeyboardInterrupt`/cancelled-gateway traceback remains noisy on SIGINT but leaves no process, retained client connection, or active service.

## 2026-08-06 — Spontaneous reply correctness and socket lifecycle Phase 1

### Runtime behavior

- Removed the prior assistant-reply excerpt from the system prompt; anti-repetition guidance remains generic and cannot leak old reply wording back to the model.
- Isolated spontaneous-reply raw history to the exact current triggering user turn while preserving separately labeled speaker, summary, structured-memory, lore, and returning-user background blocks.
- Added fail-closed validation so spontaneous prompt assembly rejects a missing or non-user current turn instead of falling back to broader history.
- Preserved existing recent-turn behavior for mentions, replies, aliases, DMs, explicit triggers, and inferred follow-ups.
- Added privacy-safe LLM request diagnostics with trigger reason, channel/message IDs, prompt role/count/size metadata, and a short SHA-256 trigger hash without raw Discord content.
- Closed each OpenAI-compatible async client in a `finally` block after success, SDK errors, cancellation, missing choices, or empty content; invalid message lists are rejected before client construction.
- Added `memory_store.json.bak*` to `.gitignore` so private local memory backups cannot be committed accidentally.

### Planning

- Added the complete two-phase spontaneous-reply/socket-lifecycle plan to `Kanban.md`.
- Phase 2 remains unimplemented: immutable pending-message snapshots, tracked shutdown-safe drain tasks, hardened Discord transcript delimiters, associated regression tests, and runtime socket/FD verification.

### Verification

- `./.venv/bin/python -m unittest tests.test_prompts tests.test_reply_request_phase1 tests.test_openai_client -v`
- Result: `Ran 21 tests` — `OK`.
- `./.venv/bin/python -m unittest discover -v`
- Result: `Ran 153 tests` — `OK`.
- `./.venv/bin/python -m compileall -q -x '(^|/)(\.venv|\.git)(/|$)' .`
- Result: compileall passed.
- `git diff --check`
- Result: clean.
- SOPPO remained offline throughout implementation and verification.

### Runtime validation

- Ran a live LM Studio smoke request, focused normal/failure-path probes, and a 50-call normal-operation soak through the real `openai_chat()` implementation.
- The 50-call soak returned 50/50 expected responses; the test process returned immediately to its `7 FD / 2 internal socket` baseline, LM Studio remained at 138 FDs, and no `ESTABLISHED` or `CLOSE_WAIT` client sockets remained.
- Isolated timeout and cancellation probes returned to baseline. A deliberately rapid mixed timeout-then-cancellation sequence intermittently retained `ESTABLISHED` client sockets until process exit but produced no `CLOSE_WAIT`; this remains a residual OpenAI-SDK timing risk for later shutdown/task-lifecycle hardening.
- Ran a supervised Discord canary with temporary process-only overrides `SPONTANEOUS_REPLY_CHANCE=1.0` and `REPLY_COOLDOWN_SECONDS=0`; `.env` was unchanged.
- Confirmed direct alias and inferred-follow-up requests retained normal context, the soft-close path cleared the follow-up latch without replying, and the true spontaneous request was logged as `reason=spontaneous` with four system/background messages, exactly one current user turn, and zero assistant turns.
- Every completed live Discord generation returned Soppo-to-LM-Studio connections to zero with no `CLOSE_WAIT` sockets.
- Sent SIGINT to the temporary canary process and verified no SOPPO process remained, both systemd units were inactive, port 1234 was listener-only, LM Studio remained at 138 FDs, and the repository contained no runtime-data changes.

## 2026-07-24 — Local memory review web UI

### Tools

- Added `tools/serve_memory_review.py`: stdlib-only local HTTP UI on `127.0.0.1:8765` (default) to review **pending** `memory_review_queue.jsonl` items, mark them approved/rejected with review metadata, and run the existing apply-approved path.
- Added `tools/serve_memory_review.py --lan` for phone/home-network review; it binds to all interfaces, prints localhost plus discovered LAN URLs, and warns that the UI has no login page.
- Added hot-apply support so approved memories can be injected without restarting `soppo-discord.service`: web UI checkbox **Hot-apply while SOPPO is running** and CLI `tools/process_memory_review_queue.py --apply-approved --hot --summary`.
- The no-restart path relies on the existing runtime refresh: `PersistentChannelSummaryMemory.reload_from_disk()` runs before structured-memory retrieval, so externally written approved memories are visible before the next relevant response.
- Extended `tools/process_memory_review_queue.py` with shared helpers: `load_queue`, `save_queue`, `queue_status_counts`, `filter_reviewable_items`, and `apply_review_decisions`.

### Docs

- Updated `README.md` and `docs/USER_MANUAL.md` with web UI startup and workflow notes.

### Verification

- `./.venv/bin/python -m compileall -q -x '(^|/)(\.venv|\.git)(/|$)' .`
- Result: compileall passed.
- `./.venv/bin/python -m unittest tests.test_serve_memory_review tests.test_process_memory_review_queue tests.test_memory_store -v`
- Result: `Ran 24 tests in 0.245s — OK`.
- `bash -n review_soppo_memory.sh`
- Result: shell syntax check passed.
- `./.venv/bin/python -m unittest discover -v`
- Result: `Ran 138 tests in 0.635s — OK`.
- `git diff --check`
- Result: clean.
- Local smoke test served a temp queue on `127.0.0.1:8766`, confirmed default page showed pending item, hid approved item, escaped HTML, and POST `/review` changed the temp item to `rejected` with `reviewed_by=web`.
- LAN smoke test served a temp queue with `--lan --port 8767`, printed `http://192.168.1.44:8767/`, confirmed `ss` was listening on `0.0.0.0:8767`, and verified the page still showed pending-only rows from localhost before the test server was killed.
- Hot-apply smoke test used a temp approved queue item and temp `memory_store.json`, ran `tools/process_memory_review_queue.py --apply-approved --hot --summary`, confirmed exit `0`, `Applied approved memories: 1`, queue status `applied`, and runtime-style `reload_from_disk()` visibility coverage in tests.

## 2026-07-16 — Family chatroom speaker-boundary cleanup

### Runtime behavior

- Kept `soppo-discord.service` offline while editing memory and prompt boundaries.
- Strengthened `prompts.py` so SOPPO/Sash may respond to Leva and other bots, but must not narrate their thoughts, actions, reactions, internal state, dialogue, or scene viewpoint.
- Updated `docs/soppo_soul.md` to scope action narration to SOPPO's own first-person body/voice and to forbid writing Leva's or another bot's actions for them.
- Rewrote the channel `1486417969083842622` summary to preserve the family-chatroom intent while making SOPPO/Sash and Leva speaker boundaries explicit.

### Verification

- `python3 -m compileall prompts.py memory.py memory_reviewer.py bot.py tests`
- Result: compileall passed.
- `python3 -m pytest tests/test_prompts.py tests/test_neutral_context_memory.py tests/test_bot_author_filtering.py -q`
- Result: `28 passed, 1 warning, 32 subtests passed in 0.46s`.
- `memory_store.json` and `user_profiles.json` parsed successfully as JSON.

## 2026-07-07 — Final memory regression coverage

### Test hardening

- Added dedicated per-user structured-memory retrieval regression tests covering guild and DM contexts.
- Verified retrieval only uses the current speaker's `discord/user/.../memories` namespace while still allowing shared/global memories to match normally.
- Added DM summary-health regressions for `discord/dm/channel/.../summary` namespace writes, deferred-below-threshold metadata, and no raw DM turn content persisted in health records.
- Marked the remaining memory-improvement Kanban test phases complete.

### Verification

- `./.venv/bin/python -m unittest tests.test_structured_memory tests.test_channel_memory -v`
- Result: targeted 36-test structured/channel-memory suite passed.
- `./.venv/bin/python -m unittest discover -v`
- Result: full 127-test suite passed.
- `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
- Result: compileall passed.
- `git diff --check`
- Result: clean.

## 2026-07-07 — Bounded DM cross-channel structured memory retrieval

### Runtime behavior

- In DMs only (`guild_id is None`), structured-memory retrieval may include lexically relevant guild/channel memories from other Discord channels so SKK can talk with SOPPO about friends while in DM.
- Cross-channel DM candidates come from `discord/guild/.../memories` namespaces only; other users' `discord/user/.../memories` namespaces remain excluded, and `soppo/global/memories` still uses the existing global lexical/reserved paths.
- Scoped current-user DM memories still fill first; cross-channel matches use remaining slots under the same small cap and lexical relevance gate.
- Structured-memory observability logs now include `selection=dm_cross_channel` for cross-channel DM picks without logging raw memory text.
- Guild/channel contexts outside DMs remain current-scope-first and do not pull unrelated cross-channel memories by default.

### Tests and verification

- Added DM cross-channel retrieval regression tests in `tests/test_structured_memory.py` for relevant friend-channel inclusion, unrelated channel exclusion, other-user privacy boundary, current-user DM memory retention, and guild-channel non-regression.
- Verification run:
  - `./.venv/bin/python -m unittest tests.test_structured_memory -v`
  - Result: targeted 23-test structured-memory suite passed.
  - `./.venv/bin/python -m unittest tests.test_field_regressions tests.test_structured_memory tests.test_memory_store -v`
  - Result: targeted 41-test field/structured/store suite passed.
  - `./.venv/bin/python -m unittest discover -v`
  - Result: full 122-test suite passed.
  - `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
  - Result: compileall passed.
  - Runtime non-content DM smoke check against local `memory_store.json` returned only selection/type metadata.

## 2026-07-07 — Memory pruning/quarantine review mode (review-only phase)

### Tooling

- Added `tools/review_memory_pruning.py` to scan structured memories in `memory_store.json` and flag review candidates without writing changes.
- Added shared helpers in `tools/memory_inspect_common.py`; `tools/inspect_memory.py` now imports the shared load/iterate/shorten/identity-term helpers.
- Review flags include: namespace/global near-duplicates, identity/body contamination terms, stale `relationship_note` records, high-hit generic/over-trigger records, and scene/joke residue stored as durable facts.
- CLI supports default text output with reason counts plus compact candidate lines, and `--json` for machine-readable review output.

### Tests and verification

- Added `tests/test_memory_pruning_review.py` with synthetic store fixtures covering all review flags, stable candidate schema, CLI `--json` output, and no-mutation guarantees.
- Verification run:
  - `./.venv/bin/python -m unittest tests.test_memory_pruning_review -v`
  - Result: targeted 12-test pruning-review suite passed.
  - `./.venv/bin/python -m unittest discover -v`
  - Result: full 118-test suite passed.
  - `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
  - Result: compileall passed.
  - Runtime dry-run against local `memory_store.json` reported 17 candidates by metadata only and confirmed the store hash was unchanged.

## 2026-07-07 — Sectioned neutral channel summaries (topic-boundary phase)

### Runtime behavior

- Updated `build_neutral_summary_messages()` to require a stable four-section neutral summary format with exact headings: `Current topic:`, `Previous/closed topics:`, `Unresolved questions / open loops:`, and `Durable facts:`.
- Added lightweight helpers in `memory.py` (`is_sectioned_neutral_summary()`, `annotate_sectioned_neutral_summary()`) to recognize sectioned summaries and insert brief boundary hints without fragile bullet parsing.
- Updated `build_channel_summary_block()` to preserve sectioned boundaries, annotate closed/previous topics as background-only, and explicitly instruct the model not to re-raise closed threads when the newest live message changes topic.
- Legacy unsectioned summaries remain backward compatible in prompt injection.
- `tools/inspect_memory.py` now prints sectioned summaries with clearer section spacing when headings are present.

### Tests and verification

- Added/adjusted tests in `tests/test_neutral_context_memory.py` for exact section headings in the summarizer prompt, sectioned block boundaries, closed-topic background regression, and legacy unsectioned compatibility.
- Verification run:
  - `./.venv/bin/python -m unittest tests.test_neutral_context_memory -v`
  - Result: targeted 15-test neutral-summary suite passed.
  - `./.venv/bin/python -m unittest discover -v`
  - Result: full 106-test suite passed.
  - `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
  - Result: compileall passed.

## 2026-07-07 — Reserved global memory retrieval (Phase 2)

### Runtime behavior

- Added configurable `RESERVED_GLOBAL_MEMORY_SLOTS` (default 2, clamped 0–5) so a bounded set of high-value global identity/canon memories can be injected without lexical overlap with the newest live user message.
- Kept lexical relevance gating for user/guild/channel memories and normal global overflow; scoped memories are selected before reserved globals consume remaining slots.
- Reserved global selection ranks by type priority (`character_note` / `relationship_note` / `project_fact`), importance, confidence, hits, and `updated_at`.
- Structured-memory observability logs now include non-content `selection` metadata (`lexical` vs `reserved_global`) without logging raw memory text.

### Tests and verification

- Added Phase 2 retrieval regression tests in `tests/test_structured_memory.py` for lexical exclusion, reserved-slot inclusion, slot caps, scoped-memory anti-crowding, and stopword-only identity probes.
- Verification run:
  - `./.venv/bin/python -m unittest tests.test_structured_memory tests.test_field_regressions tests.test_memory_store -v`
  - Result: targeted 37-test structured-memory/field/store suite passed.
  - `./.venv/bin/python -m unittest discover -v`
  - Result: full 102-test suite passed.
  - `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
  - Result: compileall passed.

## 2026-07-07 — Curated JSONL import converter (Phase 1+)

### Tooling

- Added `tools/import_memory_candidates.py` to convert curated memory JSONL rows into pending review-queue items for `tools/process_memory_review_queue.py`.
- Maps curated fields (`memory_text`, `category`, `importance_scores`, evidence) to runtime candidate schema (`type`, `scope`, `text`, `confidence`) with default namespace `soppo/global/memories`.
- Validates all input rows before writing, preserves audit metadata in queue `source`, uses stable dedup-safe item IDs, and refuses overwrite unless `--force`.
- Does not auto-apply or write directly to `memory_store.json`.

### Tests and verification

- Added `tests/test_import_memory_candidates.py` for conversion, overwrite guard, malformed JSONL fail-fast, duplicate source IDs, and category mapping.
- Verification run:
  - `./.venv/bin/python -m unittest tests.test_import_memory_candidates tests.test_process_memory_review_queue tests.test_memory_store -v`
  - Result: targeted 19-test import/store/queue suite passed.
  - `./.venv/bin/python tools/import_memory_candidates.py memory_import_queue_first_person_plus_soppo_test_candidates_edited.jsonl --output /tmp/soppo_memory_review_queue_test.jsonl --dry-run`
  - Result: converted 60 curated rows in dry-run mode: 32 character notes, 15 relationship notes, 13 project facts.
  - `./.venv/bin/python -m unittest discover -v`
  - Result: full 95-test suite passed.
  - `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
  - Result: compileall passed.

## 2026-07-07 — Memory store write safety and observability (Phase 1)

### Runtime behavior

- Made `memory_store.json` writes merge-safe and flock-locked (`memory_store.json.lock`) so stale in-memory summary saves no longer erase externally added namespaces such as `soppo/global/memories` or `discord/user/.../memories`.
- Added `PersistentChannelSummaryMemory.reload_from_disk()` / `refresh_memory_store_from_disk()` so runtime can pick up external writes before structured-memory retrieval.
- Added structured-memory retrieval observability in `bot.py`: logs count plus type/key/hash/source metadata only (no raw Discord messages or memory text).
- Hardened `tools/process_memory_review_queue.py --apply-approved` to refuse when `soppo-discord.service` is active unless `--force` is passed.

### Tests and verification

- Added regression tests for merge-safe summary metadata writes, disk refresh, and the review-queue active-service guard.
- Verification run:
  - `./.venv/bin/python -m unittest tests.test_memory_store tests.test_structured_memory tests.test_channel_memory tests.test_process_memory_review_queue -v`
  - Result: targeted 34-test memory/store/queue suite passed.
  - `./.venv/bin/python -m unittest discover -v`
  - Result: full 89-test suite passed.
  - `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
  - Result: compileall passed.

## 2026-06-29 — API-backed memory review queue

### Runtime behavior

- Added optional background/API clerical backends so neutral summaries and memory review can use OpenAI while live SOPPO replies stay on the configured local personality backend.
- Added `memory_reviewer.py`: API proposes structured memory candidates, then local code checks candidate type/scope/confidence, identity/roleplay risk, existing `memory_store.json`, and ignored `user_profiles.json` before writing anything.
- Safe non-conflicting candidates are applied to `memory_store.json` with source `api_memory_review`; exact duplicates are dropped; conflicts/risky/profile-overlap candidates go to `memory_review_queue.jsonl` for human review.
- Added `tools/process_memory_review_queue.py` to summarize pending queue items and apply entries manually marked `approved`.
- Added `.env.example` settings for `SUMMARY_LLM_BACKEND`, `MEMORY_REVIEW_ENABLED`, `MEMORY_REVIEW_LLM_BACKEND`, and review queue paths; `memory_review_queue.jsonl` is git-ignored.

### Verification

- `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
- `./.venv/bin/python -m unittest tests.test_neutral_context_memory tests.test_structured_memory -v`
- Result: targeted 24-test summary/memory suite passed; compileall passed.

## 2026-06-29 — Reply coalescing for slow LLM backlog control

### Runtime behavior

- Added per-channel reply coalescing so a slow LM Studio generation does not queue every latch-eligible message behind it.
- While a channel reply is active, SOPPO keeps only one latest useful pending message for that channel instead of starting another waiting LLM request.
- Pending priority is: identity reset > direct address/mention/reply/trigger/name alias > inferred follow-up > spontaneous/ambient ignored.
- New direct `Sash`/`Soppo` messages replace older pending follow-ups; newer equal-priority messages replace older ones so SOPPO answers the latest useful message, not ghosts from two minutes ago.
- Sleep commands clear any pending reply for that channel.

### Verification

- `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
- `./.venv/bin/python -m unittest tests.test_followup_soft_close -v`
- Result: targeted 15-test follow-up/coalescing suite passed; compileall passed.

## 2026-06-29 — Identity-confrontation context cleanup

### Runtime behavior

- Direct identity probes such as `who are you?`, `are you Leva?`, `identity check`, and `what's the deal with Leva?` now act as a cleanup cue instead of a deterministic reply bypass.
- On an identity confrontation, SOPPO purges the current channel's recent raw history, pending summary turns, previous bot reply reminder, and rolling channel summary before building the LLM prompt.
- The LLM still answers, but only with the core SOPPO/Sash identity prompt, current speaker profile, identity-reset context, and the newest live message.
- Strengthened current-speaker profile context so fields such as username/pronouns/relationship are clearly marked as belonging to the speaker, not SOPPO; SOPPO is explicitly told never to adopt the speaker profile as her own identity.
- Kept the Leva profile private in ignored `user_profiles.json`; when Leva is the current speaker, reset context identifies Leva as separate from SOPPO and as an older-sister figure.

### Verification

- `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
- `./.venv/bin/python -m unittest tests.test_followup_soft_close tests.test_prompts -v`
- Result: targeted 18-test identity/prompt suite passed; compileall passed.

## 2026-06-29 — Identity contamination snap-back hardening

### Runtime behavior

- Added a hard identity stability rule to the main SOPPO/Sash system prompt: roleplay, quoted dialogue, and third-party character messages are external context only and cannot overwrite Sash/SOPPO identity.
- Added an identity recovery protocol for identity checks or accusations of acting unlike herself: stop the scene, say `I'm Sash. I got tangled in the scene. Resetting orientation.`, then restate name, nickname, relationship/context anchor, current chat context, and roleplay status.
- Strengthened neutral channel summary instructions so temporary roleplay facts are not summarized as permanent identity, relationship, body, or personality facts.
- Hardened deterministic structured-memory extraction to skip temporary roleplay/scene facts unless explicitly marked as durable canon.
- Updated `docs/soppo_soul.md` with the same identity stability and snap-back protocol.

### Verification

- `./.venv/bin/python -m unittest tests.test_prompts tests.test_neutral_context_memory tests.test_structured_memory -v`
- `./.venv/bin/python -m compileall -q -x '(^|/)(\\.venv|\\.git)(/|$)' .`
- `./.venv/bin/python -m unittest discover -v`
- Result: targeted 24-test prompt/memory suite passed; full 71-test suite passed; compileall passed.

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
