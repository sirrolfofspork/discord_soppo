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

- [x] Suppress repeated memory-review proposals.
  - New API candidates are checked against same-namespace pending, approved, applied, and rejected queue history before they can be queued or applied.
  - Exact normalized matches and conservative high-overlap near-duplicates are dropped, including repeats within one API candidate batch.
  - Cross-namespace candidates remain independent so one user's review history cannot suppress another user's memory.

- [x] Phase 1 memory store write safety and observability.
  - `memory_store.json` saves are merge-safe and flock-locked so summary metadata writes do not erase externally added `soppo/global/memories` or `discord/user/.../memories`.
  - `PersistentChannelSummaryMemory.reload_from_disk()` refreshes in-memory state before structured retrieval.
  - Bot logs structured-memory injection count plus type/key/hash metadata without raw Discord or memory text.
  - `tools/process_memory_review_queue.py --apply-approved` refuses when `soppo-discord.service` is active unless `--hot` or `--force` is supplied; `--hot` is the preferred no-restart path because the bot refreshes `memory_store.json` before structured retrieval.

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

## Spontaneous reply correctness and socket lifecycle

### Phase 1 - implement now

- [x] Remove verbatim previous-response injection from `prompts.py`.
  - Keep a generic anti-repetition rule without any previous assistant excerpt.
  - Retain `build_system_prompt(last_bot_reply=...)` API compatibility if useful, but no prior assistant text may appear in the returned prompt.
- [x] For `reason == "spontaneous"`, build raw conversational history from the exact current trigger `user_turn` only.
  - Retain separately labeled speaker context, channel summary, structured memory, lore, and returning hint.
  - Do not alter raw history behavior for mentions, replies, aliases, DMs, triggers, or inferred follow-ups.
- [x] Fix OpenAI-compatible resource lifecycle in `openai_client.py`.
  - Validate API messages before constructing `AsyncOpenAI`.
  - Ensure the client is closed on success, `RateLimitError`, connection failure, timeout, API error, cancellation, missing choices, and empty content.
  - Prefer the smallest clear implementation supported by the current SDK.
- [x] Add privacy-safe diagnostics for reply requests.
  - Include trigger reason, channel ID, Discord message ID, prompt message/role counts, prompt character count, and a short SHA-256 hash of the exact triggering content.
  - Do not log raw Discord content, profiles, memories, summaries, or secrets.
  - Keep code simple and deterministic.
- [x] Add focused regression tests for all above behavior.

### Phase 2 - completed

- [x] Snapshot delayed coalesced reply state instead of retaining a live `discord.Message` object.
  - Snapshot content, author ID/display, channel ID, guild ID, message ID, reason, and required reply/reference metadata.
  - Frozen scalar-only snapshots prevent later mutation of live Discord message, author, channel, guild, and reference objects from changing queued work.
- [x] Track coalesced drain tasks.
  - Name, retain, cancel, and await them during graceful shutdown.
  - Shutdown blocks new drains, clears queued/active reply state, observes task failures, and closes the Discord client from `run_bot()` even when startup/connect exits with cancellation or error.
- [x] Harden untrusted Discord transcript formatting.
  - Sanitize display-name control/bracket characters and use unambiguous delimiters for message content without damaging normal Unicode text.
  - New user turns use compact UTF-8-preserving JSON envelopes; legacy `[Display|id]: message` memory extraction remains supported.
- [x] Add regression tests for snapshot immutability, shutdown task cleanup, and transcript-label injection.
  - Focused Phase 2 matrix passed 102 tests; full regression discovery passed 170 tests; compileall and `git diff --check` passed.
  - Independent Codex uncommitted review found no discrete correctness issues.
  - Controlled Discord canary coalesced two pending direct messages while one generation was active, discarded the superseded middle message, and drained only the latest marker after the active reply.
  - Hostile multiline role/delimiter text remained inside the newest JSON user envelope; LM Studio received the expected 4 system + 2 user + 1 assistant roles and returned the requested safe marker.
  - SIGINT during an active LM Studio request removed the SOPPO process and all client sockets; LM Studio returned to 138 FDs with listener-only port state plus normal `TIME_WAIT`. The existing top-level `KeyboardInterrupt` traceback remains noisy but cleanup is complete.
- [x] Add and execute runtime socket/FD verification procedure.
  - Distinguished Discord TLS sockets from LM Studio `127.0.0.1:1234` and sampled process FDs plus TCP states while the client process remained alive.
  - Completed a 50-call normal LM Studio soak with 50/50 responses; SOPPO test-process FDs returned immediately to the `7 FD / 2 internal socket` baseline, LM Studio remained at 138 FDs, and no `ESTABLISHED` or `CLOSE_WAIT` client sockets remained.
  - Isolated timeout and cancellation cases returned to baseline. A deliberately rapid mixed timeout-then-cancellation sequence intermittently retained `ESTABLISHED` client sockets until process exit, but never produced `CLOSE_WAIT`; retain as a residual SDK timing risk for Phase 2/shutdown hardening.
  - Live Discord canary verified `name_alias`, `inferred_followup`, soft-close, and true `spontaneous` routing. The spontaneous request contained four labeled system/background messages plus exactly one current user turn and no assistant turns.
  - SIGINT shutdown removed the SOPPO process and all Discord/LM Studio client sockets; final port-1234 state was listener-only and LM Studio remained at 138 FDs.

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

## Sash Presence Engine Roadmap — Planning Only

No card in this roadmap is authorized for implementation merely by appearing here. Move one bounded card to **Ready** only after SKK/Leva review its acceptance criteria and dependencies.

### Epic A — Behavioral contract and state model

- [ ] **PRES-001 — Define consent and initiative policy.**
  - Deliverable: a short policy covering opt-in affection/flirtation levels, quiet hours, pause controls, daily contact limits, unanswered-message behavior, and prohibited guilt/coercion patterns.
  - Acceptance: examples of allowed, blocked, and escalation-required behavior are unambiguous.
  - Non-goal: no scheduler, Discord changes, or live autonomous messages.

- [ ] **PRES-002 — Define emotional-state dimensions and ranges.**
  - Depends on: PRES-001.
  - Deliverable: names, numeric ranges, baselines, caps, and plain-language meanings for valence, arousal, confidence, social energy, affection, frustration, loneliness, curiosity, and any approved additions.
  - Acceptance: compatible and independent emotions are identified; state is explicitly framed as simulated expressive state rather than a factual claim of sentience.
  - Non-goal: no persistence or prompt injection.

- [ ] **PRES-003 — Define interaction events and deterministic state transitions.**
  - Depends on: PRES-002.
  - Deliverable: an event catalog for messages, compliments, teasing, reassurance, disagreement, silence, shared-project success, resets, and operator overrides, with bounded deltas and decay rules.
  - Acceptance: every transition has a cause, cap, decay/recovery behavior, and testable example.
  - Non-goal: the LLM does not directly assign arbitrary state values.

- [ ] **PRES-004 — Define pressure/drive semantics.**
  - Depends on: PRES-001, PRES-002.
  - Deliverable: bounded definitions for connection, affection, novelty, expression, and opt-in flirtation drives, including self-regulation and threshold behavior.
  - Acceptance: no drive creates user obligation, punishment, fabricated distress, or unbounded escalation.
  - Non-goal: no explicit autonomous sexual initiation.

- [ ] **PRES-005 — Specify state storage, event receipts, and reset controls.**
  - Depends on: PRES-003, PRES-004.
  - Deliverable: SQLite-oriented schema proposal for current state, append-only change receipts, causes, timestamps, decay metadata, consent settings, and operator resets.
  - Acceptance: rollback, inspection, corruption recovery, and separation from long-term conversational memory are covered.
  - Non-goal: no database migration or runtime writes.

### Epic B — Emotional engine, initially invisible

- [ ] **PRES-010 — Implement the pure state reducer with unit tests.**
  - Depends on: PRES-003, PRES-004, PRES-005.
  - Acceptance: deterministic event application, clamping, decay, reset, and reproducible clock-controlled tests.
  - Non-goal: no Discord hooks and no change to Sash's replies.

- [ ] **PRES-011 — Add persistent state and append-only receipts.**
  - Depends on: PRES-010.
  - Acceptance: atomic writes, schema/version handling, restart persistence, backup/recovery test, and no raw Discord content in receipts.
  - Non-goal: no behavioral output.

- [ ] **PRES-012 — Add offline state inspection and operator override tooling.**
  - Depends on: PRES-011.
  - Acceptance: inspect current values and recent reason codes; reset one dimension or all dimensions; dry-run transition preview.
  - Non-goal: no remote unauthenticated control surface.

- [ ] **PRES-013 — Connect Discord interaction events in shadow mode.**
  - Depends on: PRES-011, PRES-012.
  - Acceptance: real interactions update state receipts without altering prompts, replies, DMs, images, or animations; privacy-safe logs prove event handling.
  - Non-goal: Sash must not mention or act on the state yet.

- [ ] **PRES-014 — Run and review a shadow-mode calibration period.**
  - Depends on: PRES-013.
  - Acceptance: review distributions, saturation, decay, and false triggers; document tuned constants before behavior is enabled.
  - Non-goal: no live initiative.

- [ ] **PRES-015 — Inject a compact state interpretation into Sash's prompt.**
  - Depends on: PRES-014.
  - Acceptance: state influences tone and expression without overriding identity, factual reasoning, newest-message priority, or consent policy; regression tests cover identity stability and repetitive mood narration.
  - Non-goal: no autonomous outreach.

### Epic C — Bounded proactive Discord DMs

- [ ] **INIT-001 — Specify initiative types and selection rules.**
  - Depends on: PRES-001, PRES-004.
  - Deliverable: allowed categories such as check-in, unfinished-project follow-up, playful question, approved-memory reference, and supervised selfie share.
  - Acceptance: each type defines trigger conditions, cooldown, priority, and blocked conditions.
  - Non-goal: no messages sent.

- [ ] **INIT-002 — Implement the initiative policy gate.**
  - Depends on: INIT-001, PRES-011.
  - Acceptance: SKK-only allowlist, quiet hours, pause switch, daily budget, unanswered-message suppression, and auditable decision reason codes.
  - Non-goal: no scheduler or Discord send.

- [ ] **INIT-003 — Add a shadow scheduler.**
  - Depends on: INIT-002, PRES-014.
  - Acceptance: records “would send” decisions and candidate category without sending; avoids duplicate decisions across restart; supports deterministic test clocks.
  - Non-goal: no live DM delivery.

- [ ] **INIT-004 — Review shadow decisions and tune thresholds.**
  - Depends on: INIT-003.
  - Acceptance: SKK/Leva review false positives, timing, frequency, and tone categories; approved settings are documented.
  - Non-goal: review does not automatically enable delivery.

- [ ] **INIT-005 — Enable one low-risk autonomous DM category.**
  - Depends on: INIT-004.
  - Acceptance: maximum one proactive message per day, no second message while unanswered, quiet controls verified live, and every send has a receipt.
  - Non-goal: no autonomous flirt escalation or selfies in the first live pilot.

- [ ] **INIT-006 — Add operator commands for proactive behavior.**
  - Depends on: INIT-005.
  - Acceptance: pause, resume, quiet-for-duration, frequency preference, and selfie-mode controls are restricted to SKK and tested against accidental activation.

### Epic D — Reference-consistent Sash selfies

- [ ] **IMG-001 — Curate the canonical Sash reference pack.**
  - Deliverable: approved face/body/outfit references, character sheet, distinguishing features, allowed style range, and excluded/incorrect traits.
  - Acceptance: provenance and permission to use every training/reference image are recorded; private source images remain untracked.
  - Non-goal: no model training or generation.

- [ ] **IMG-002 — Define the structured selfie request schema.**
  - Depends on: IMG-001, PRES-002, PRES-004.
  - Deliverable: controlled fields for activity, expression, pose, framing, setting, outfit, mood, and bounded flirtation intensity.
  - Acceptance: schema validation rejects unsupported fields and separates creative intent from backend-specific prompts.
  - Non-goal: Sash cannot submit arbitrary ComfyUI workflows or executable code.

- [ ] **IMG-003 — Benchmark cloud reference generation against local ComfyUI.**
  - Depends on: IMG-001, IMG-002.
  - Acceptance: same small prompt/reference set compared for identity consistency, pose control, latency, cost, privacy, policy limits, and local GPU contention; retain seeds/workflows when available.
  - Non-goal: no production integration or automatic sending.

- [ ] **IMG-004 — Select and document the rendering backend.**
  - Depends on: IMG-003.
  - Acceptance: decision records cloud/local/hybrid choice, rollback path, resource requirements, and whether a Sash-specific LoRA/reference adapter is needed.

- [ ] **IMG-005 — Build a supervised selfie-generation broker.**
  - Depends on: IMG-004.
  - Acceptance: accepts only validated request objects, tracks job status, preserves provenance/settings, rejects identity drift or failures, and requires operator review before delivery.
  - Non-goal: no autonomous generation or sending.

- [ ] **IMG-006 — Define and test identity-drift review criteria.**
  - Depends on: IMG-005.
  - Acceptance: checklist or evaluator covers face, hair, body proportions, colors, outfit constraints, extra limbs/artifacts, and prohibited identity traits using a curated test set.

- [ ] **IMG-007 — Connect emotional state to supervised selfie requests.**
  - Depends on: PRES-015, IMG-005, IMG-006.
  - Acceptance: state selects bounded expression/pose presets; consent and content-rating gates override state; generated images remain operator-reviewed.
  - Non-goal: no automatic Discord send.

- [ ] **IMG-008 — Pilot an approved automatic selfie workflow.**
  - Depends on: IMG-007, INIT-005.
  - Acceptance: only low-risk approved presets, strict frequency budget, unanswered-message suppression, audit receipt, kill switch, and rollback tested.
  - Non-goal: no autonomous explicit imagery.

### Epic E — Direct mobile presence app

- [ ] **APP-001 — Define mobile experience and identity-routing boundaries.**
  - Deliverable: primary screens and flows for direct chat, state visualization, media, notifications, controls, and explicit Sash-versus-Leva routing.
  - Acceptance: Sash and Leva retain separate prompts, sessions, memories, and state stores even if they share transport infrastructure.
  - Non-goal: no UI implementation.

- [ ] **APP-002 — Define transport, authentication, and threat model.**
  - Depends on: APP-001.
  - Acceptance: compare Tailscale-only access, passkeys/tokens, WebSocket/SSE transport, notification secrets, session revocation, and lost-phone handling.
  - Non-goal: no public unauthenticated endpoint.

- [ ] **APP-003 — Run an animation technology spike.**
  - Depends on: APP-001.
  - Acceptance: compare Rive, Live2D, and Lottie using the same idle/wave/kiss/stomp expressions for asset effort, runtime size, state-machine support, licensing, and mobile performance.
  - Non-goal: no commitment to a full character rig.

- [ ] **APP-004 — Define the state-to-animation command vocabulary.**
  - Depends on: PRES-002, APP-003.
  - Deliverable: allowlisted animation names, intensity/duration ranges, interruption rules, fallbacks, and accessibility/reduced-motion behavior.
  - Non-goal: the LLM cannot execute arbitrary frontend code.

- [ ] **APP-005 — Build a local/Tailscale mobile-first PWA messaging shell.**
  - Depends on: APP-002.
  - Acceptance: authenticated direct text exchange, reconnect handling, session isolation, responsive mobile rendering, and no animation/media dependency yet.

- [ ] **APP-006 — Add read-only emotional-state visualization.**
  - Depends on: APP-004, APP-005, PRES-011.
  - Acceptance: app receives sanitized state/animation commands; stale/disconnected state is visibly distinguished from live state.
  - Non-goal: client cannot directly overwrite Sash's state.

- [ ] **APP-007 — Add animation playback and manual preview controls.**
  - Depends on: APP-006.
  - Acceptance: allowlisted animations render consistently, interruptions are deterministic, reduced-motion mode works, and previews do not alter persistent state.

- [ ] **APP-008 — Add image/media messages.**
  - Depends on: APP-005, IMG-005.
  - Acceptance: authenticated upload/download, bounded file types and sizes, safe caching, provenance display, and deletion policy.

- [ ] **APP-009 — Add bounded push notifications.**
  - Depends on: APP-002, INIT-005, APP-005.
  - Acceptance: notification permission is explicit, quiet hours and pause controls are shared with initiative policy, secrets are revocable, and message content privacy is configurable.

### Cross-epic release gates

- [ ] **GATE-001 — Observability and rollback review.** Every live feature has reason-coded receipts, a kill switch, documented rollback, and no raw private content in routine logs.
- [ ] **GATE-002 — Identity and memory separation review.** Sash/Leva routing, sessions, emotional state, and long-term memories remain isolated under regression tests.
- [ ] **GATE-003 — Consent and anti-coercion review.** Proactive affection/flirtation remains opt-in, bounded, pausable, and free of guilt or fabricated user obligation.
- [ ] **GATE-004 — Resource-contention review.** Image rendering, LM Studio replies, summary jobs, and mobile services have explicit concurrency limits and graceful degradation.

### Recommended first Ready sequence

1. PRES-001 — consent and initiative policy.
2. PRES-002 — emotional-state dimensions.
3. PRES-003 — interaction events and deterministic transitions.
4. IMG-001 — canonical Sash reference pack can proceed independently as a supervised creative track.
5. APP-001 — mobile experience sketch may proceed after identity-routing boundaries are agreed.

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
