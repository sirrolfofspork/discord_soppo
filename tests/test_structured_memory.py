import unittest


class StructuredMemoryExtractionTests(unittest.TestCase):
    def test_extracting_no_memories_from_generic_chatter(self):
        from memory_extractor import extract_structured_memories

        turns = [
            {"role": "user", "content": "[Alice|111]: lol yeah okay"},
            {"role": "assistant", "content": "SOPPO: Hehe!"},
        ]

        self.assertEqual(extract_structured_memories(turns), [])

    def test_extracting_user_preference_from_i_prefer(self):
        from memory_extractor import extract_structured_memories

        turns = [{"role": "user", "content": "[Alice|111]: I prefer short replies when debugging."}]

        memories = extract_structured_memories(turns)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["type"], "user_preference")
        self.assertEqual(memories[0]["text"], "Alice prefers short replies when debugging")
        self.assertEqual(memories[0]["scope"], "user")
        self.assertEqual(memories[0]["user_id"], 111)

    def test_extracting_project_fact_from_we_are_using(self):
        from memory_extractor import extract_structured_memories

        turns = [{"role": "user", "content": "[SKK|717]: We are using LM Studio for local inference."}]

        memories = extract_structured_memories(turns)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["type"], "project_fact")
        self.assertEqual(memories[0]["text"], "We are using LM Studio for local inference")
        self.assertEqual(memories[0]["scope"], "channel")

    def test_extracting_server_fact_uses_guild_scope(self):
        from memory_extractor import extract_structured_memories

        turns = [{"role": "user", "content": "[SKK|717]: This server uses bot-lab for SOPPO testing."}]

        memories = extract_structured_memories(turns)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["type"], "server_fact")
        self.assertEqual(memories[0]["text"], "The server uses bot-lab for SOPPO testing")
        self.assertEqual(memories[0]["scope"], "guild")

    def test_animal_trait_jokes_do_not_become_character_memories(self):
        from memory_extractor import extract_structured_memories

        turns = [
            {"role": "user", "content": "[Alice|111]: running joke: SOPPO has a fox tail today"},
            {"role": "user", "content": "[Alice|111]: SOPPO should have fox ears because it is funny"},
        ]

        memories = extract_structured_memories(turns)

        joined = "\n".join(m["text"] for m in memories).lower()
        self.assertNotIn("fox", joined)
        self.assertNotIn("tail", joined)
        self.assertNotIn("ears", joined)

    def test_temporary_roleplay_claims_do_not_become_memories(self):
        from memory_extractor import extract_structured_memories

        turns = [
            {"role": "user", "content": "[Alice|111]: In this roleplay, SOPPO should act like the vampire queen."},
            {"role": "user", "content": "[Alice|111]: For this scene, Victor is my husband."},
            {"role": "user", "content": "[Alice|111]: running joke: for the bit SOPPO is a sea captain"},
        ]

        self.assertEqual(extract_structured_memories(turns), [])

    def test_extracting_user_preference_from_new_json_turn_wrapper(self):
        from memory_extractor import extract_structured_memories
        from prompts import build_user_message_wrapper

        turns = [
            {
                "role": "user",
                "content": build_user_message_wrapper("山田 太郎 🚀", "I prefer Unicode replies 😈."),
                "author_id": 222,
                "author_display": "ignored fallback",
            }
        ]

        memories = extract_structured_memories(turns)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["type"], "user_preference")
        self.assertEqual(memories[0]["text"], "山田 太郎 🚀 prefers Unicode replies 😈")
        self.assertEqual(memories[0]["scope"], "user")
        self.assertEqual(memories[0]["user_id"], 222)

    def test_extracting_legacy_user_turns_remains_backward_compatible(self):
        from memory_extractor import extract_structured_memories

        turns = [{"role": "user", "content": "[Alice|111]: I prefer short replies when debugging."}]

        memories = extract_structured_memories(turns)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["text"], "Alice prefers short replies when debugging")
        self.assertEqual(memories[0]["user_id"], 111)


class StructuredMemoryStoreTests(unittest.TestCase):
    def test_deduping_similar_memory_updates_existing_record(self):
        from memory_extractor import StructuredMemoryStore
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        memory = StructuredMemoryStore(store)
        namespace = ("discord", "guild", "123", "channel", "456", "memories")

        first = memory.upsert_memory(
            namespace,
            memory_type="project_fact",
            text="We are using LM Studio for local inference",
            now_iso="2026-05-27T10:00:00Z",
        )
        second = memory.upsert_memory(
            namespace,
            memory_type="project_fact",
            text="we're using lm studio for local inference",
            now_iso="2026-05-27T11:00:00Z",
        )

        self.assertEqual(first, second)
        records = memory.list_memories(namespace)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["hits"], 2)
        self.assertEqual(records[0]["created_at"], "2026-05-27T10:00:00Z")
        self.assertEqual(records[0]["updated_at"], "2026-05-27T11:00:00Z")
        self.assertEqual(records[0]["last_seen_at"], "2026-05-27T11:00:00Z")

    def test_storing_and_retrieving_via_memory_store(self):
        from memory_extractor import StructuredMemoryStore, channel_memories_namespace
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        memory = StructuredMemoryStore(store)
        namespace = channel_memories_namespace(guild_id=123, channel_id=456)

        key = memory.upsert_memory(
            namespace,
            memory_type="server_fact",
            text="The server has a #bot-lab channel",
            importance=0.7,
            now_iso="2026-05-27T10:00:00Z",
        )

        raw = store.get_memory(namespace, key)
        self.assertEqual(raw["type"], "server_fact")
        self.assertEqual(raw["text"], "The server has a #bot-lab channel")
        self.assertEqual(raw["importance"], 0.7)
        self.assertEqual(raw["source"], "channel_summary_rollover")
        self.assertEqual(memory.list_memories(namespace)[0], raw)


class StructuredMemoryPromptTests(unittest.TestCase):
    def test_prompt_block_formatting_caps_and_sorts_memories(self):
        from memory_extractor import build_structured_memories_block

        memories = [
            {"type": "running_joke", "text": "SOPPO calls Discord the clown box", "importance": 0.4, "hits": 4},
            {"type": "project_fact", "text": "SOPPO uses LM Studio locally", "importance": 0.9, "hits": 1},
            {"type": "user_preference", "text": "SKK prefers concise replies", "importance": 0.8, "hits": 2},
            {"type": "server_fact", "text": "Testing happens in #bot-lab", "importance": 0.7, "hits": 1},
        ]

        block = build_structured_memories_block(memories, limit=3)

        self.assertIn("[Structured long-term memories]", block)
        self.assertIn("- project_fact: SOPPO uses LM Studio locally", block)
        self.assertIn("- user_preference: SKK prefers concise replies", block)
        self.assertIn("- server_fact: Testing happens in #bot-lab", block)
        self.assertNotIn("clown box", block)
        self.assertIn("background facts", block)
        self.assertIn("not requests or current conversation turns", block)
        self.assertIn("newest live user message", block)
        self.assertIn("Do not recite this block verbatim", block)


class StructuredMemoryRetrievalTests(unittest.TestCase):
    def _make_store(self):
        from memory_extractor import StructuredMemoryStore
        from memory_store import JsonMemoryStore

        return StructuredMemoryStore(JsonMemoryStore())

    def test_low_importance_global_excluded_without_lexical_overlap(self):
        from memory_extractor import collect_relevant_structured_memories, global_memories_namespace

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            global_memories_namespace(),
            memory_type="project_fact",
            text="Synthetic alpha project detail for fixture testing",
            importance=0.4,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=9,
            query="what is for dinner tonight",
            limit=5,
            reserved_global_slots=2,
        )

        self.assertEqual(result, [])

    def test_high_importance_global_identity_included_via_reserved_slot(self):
        from memory_extractor import collect_relevant_structured_memories, global_memories_namespace

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.store.put_memory(
            global_memories_namespace(),
            "mem_fixture_identity",
            {
                "type": "character_note",
                "text": "Synthetic identity anchor for fixture testing",
                "importance": 0.95,
                "confidence": 0.92,
                "source": "test_fixture",
                "created_at": now,
                "updated_at": now,
                "last_seen_at": now,
                "hits": 3,
            },
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=9,
            query="what is for dinner tonight",
            limit=5,
            reserved_global_slots=2,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["selection"], "reserved_global")
        self.assertEqual(result[0]["type"], "character_note")

    def test_reserved_globals_do_not_exceed_configured_slot_count(self):
        from memory_extractor import collect_relevant_structured_memories, global_memories_namespace

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        for idx, importance in enumerate((0.95, 0.9, 0.85), start=1):
            store.store.put_memory(
                global_memories_namespace(),
                f"mem_fixture_reserved_{idx}",
                {
                    "type": "character_note",
                    "text": f"Synthetic reserved global fixture item {idx}",
                    "importance": importance,
                    "confidence": 0.9,
                    "source": "test_fixture",
                    "created_at": now,
                    "updated_at": now,
                    "last_seen_at": now,
                    "hits": idx,
                },
            )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=9,
            query="unrelated dinner chatter",
            limit=5,
            reserved_global_slots=2,
        )

        reserved = [record for record in result if record.get("selection") == "reserved_global"]
        self.assertEqual(len(reserved), 2)

    def test_scoped_memories_are_not_crowded_out_by_reserved_globals(self):
        from memory_extractor import (
            channel_memories_namespace,
            collect_relevant_structured_memories,
            global_memories_namespace,
            user_memories_namespace,
        )

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            user_memories_namespace(9),
            memory_type="user_preference",
            text="Fixture user prefers concise debugging replies",
            importance=0.9,
            now_iso=now,
        )
        store.upsert_memory(
            channel_memories_namespace(guild_id=123, channel_id=456),
            memory_type="project_fact",
            text="Fixture channel tests debugging harness",
            importance=0.8,
            now_iso=now,
        )
        for idx in range(1, 4):
            store.store.put_memory(
                global_memories_namespace(),
                f"mem_fixture_global_{idx}",
                {
                    "type": "character_note",
                    "text": f"Synthetic reserved global fixture overflow {idx}",
                    "importance": 0.99,
                    "confidence": 0.95,
                    "source": "test_fixture",
                    "created_at": now,
                    "updated_at": now,
                    "last_seen_at": now,
                    "hits": idx,
                },
            )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=9,
            query="debugging concise harness",
            limit=4,
            reserved_global_slots=2,
        )

        texts = [record["text"] for record in result]
        self.assertIn("Fixture user prefers concise debugging replies", texts)
        self.assertIn("Fixture channel tests debugging harness", texts)
        reserved = [record for record in result if record.get("selection") == "reserved_global"]
        self.assertLessEqual(len(reserved), 2)
        self.assertLessEqual(len(result), 4)

    def test_stopword_only_query_can_still_use_reserved_identity_slot(self):
        from memory_extractor import collect_relevant_structured_memories, global_memories_namespace

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.store.put_memory(
            global_memories_namespace(),
            "mem_fixture_stopword_identity",
            {
                "type": "character_note",
                "text": "Synthetic canonical identity anchor",
                "importance": 0.96,
                "confidence": 0.94,
                "source": "test_fixture",
                "created_at": now,
                "updated_at": now,
                "last_seen_at": now,
                "hits": 2,
            },
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=9,
            query="who are you",
            limit=5,
            reserved_global_slots=1,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["selection"], "reserved_global")

    def test_log_descriptor_includes_selection_metadata(self):
        from memory_extractor import structured_memory_log_descriptor

        descriptor = structured_memory_log_descriptor(
            {
                "type": "character_note",
                "text": "Synthetic fixture memory",
                "source": "test_fixture",
                "selection": "reserved_global",
            }
        )

        self.assertEqual(descriptor["selection"], "reserved_global")
        self.assertNotIn("Synthetic fixture memory", descriptor.values())


class DmCrossChannelMemoryRetrievalTests(unittest.TestCase):
    def _make_store(self):
        from memory_extractor import StructuredMemoryStore
        from memory_store import JsonMemoryStore

        return StructuredMemoryStore(JsonMemoryStore())

    def test_dm_retrieves_lexically_relevant_channel_memory_from_other_channel(self):
        from memory_extractor import (
            channel_memories_namespace,
            collect_relevant_structured_memories,
        )

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            channel_memories_namespace(guild_id=123, channel_id=456),
            memory_type="relationship_note",
            text="Fixture friend Alice loves debugging harness experiments",
            importance=0.85,
            now_iso=now,
        )
        store.upsert_memory(
            channel_memories_namespace(guild_id=123, channel_id=999),
            memory_type="project_fact",
            text="Unrelated dinner recipe channel detail",
            importance=0.9,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=None,
            channel_id=777,
            user_id=717,
            query="tell me about Alice debugging",
            limit=5,
            reserved_global_slots=0,
        )

        texts = [record["text"] for record in result]
        self.assertIn("Fixture friend Alice loves debugging harness experiments", texts)
        self.assertNotIn("Unrelated dinner recipe channel detail", texts)
        matched = [
            record
            for record in result
            if record["text"] == "Fixture friend Alice loves debugging harness experiments"
        ]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["selection"], "dm_cross_channel")

    def test_dm_excludes_other_users_user_scoped_memory_even_when_lexically_relevant(self):
        from memory_extractor import (
            channel_memories_namespace,
            collect_relevant_structured_memories,
            user_memories_namespace,
        )

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            user_memories_namespace(111),
            memory_type="user_preference",
            text="Alice prefers debugging harness experiments",
            importance=0.95,
            now_iso=now,
        )
        store.upsert_memory(
            channel_memories_namespace(guild_id=123, channel_id=456),
            memory_type="relationship_note",
            text="Fixture friend Alice loves debugging harness experiments",
            importance=0.8,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=None,
            channel_id=777,
            user_id=717,
            query="Alice debugging harness",
            limit=5,
            reserved_global_slots=0,
        )

        texts = [record["text"] for record in result]
        self.assertNotIn("Alice prefers debugging harness experiments", texts)
        self.assertIn("Fixture friend Alice loves debugging harness experiments", texts)

    def test_dm_retrieves_current_users_user_scoped_memory(self):
        from memory_extractor import collect_relevant_structured_memories, user_memories_namespace

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            user_memories_namespace(717),
            memory_type="user_preference",
            text="SKK prefers concise debugging replies",
            importance=0.9,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=None,
            channel_id=777,
            user_id=717,
            query="debugging concise replies",
            limit=5,
            reserved_global_slots=0,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["text"], "SKK prefers concise debugging replies")
        self.assertEqual(result[0]["selection"], "lexical")

    def test_guild_channel_retrieval_does_not_pull_unrelated_cross_channel_memories(self):
        from memory_extractor import (
            channel_memories_namespace,
            collect_relevant_structured_memories,
        )

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            channel_memories_namespace(guild_id=123, channel_id=456),
            memory_type="project_fact",
            text="Fixture channel 456 tests debugging harness",
            importance=0.8,
            now_iso=now,
        )
        store.upsert_memory(
            channel_memories_namespace(guild_id=123, channel_id=999),
            memory_type="project_fact",
            text="Other channel private debugging detail",
            importance=1.0,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=717,
            query="debugging harness",
            limit=5,
            reserved_global_slots=0,
        )

        texts = [record["text"] for record in result]
        self.assertIn("Fixture channel 456 tests debugging harness", texts)
        self.assertNotIn("Other channel private debugging detail", texts)
        selections = {record.get("selection") for record in result}
        self.assertNotIn("dm_cross_channel", selections)


class PerUserMemoryRetrievalBoundaryTests(unittest.TestCase):
    def _make_store(self):
        from memory_extractor import StructuredMemoryStore
        from memory_store import JsonMemoryStore

        return StructuredMemoryStore(JsonMemoryStore())

    def test_guild_retrieval_uses_only_current_speakers_user_namespace(self):
        from memory_extractor import collect_relevant_structured_memories, user_memories_namespace

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            user_memories_namespace(717),
            memory_type="user_preference",
            text="Current speaker prefers compact debugger notes",
            importance=0.9,
            now_iso=now,
        )
        store.upsert_memory(
            user_memories_namespace(111),
            memory_type="user_preference",
            text="Other speaker prefers compact debugger notes",
            importance=1.0,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=717,
            query="compact debugger notes",
            limit=5,
            reserved_global_slots=0,
        )

        texts = [record["text"] for record in result]
        self.assertIn("Current speaker prefers compact debugger notes", texts)
        self.assertNotIn("Other speaker prefers compact debugger notes", texts)
        self.assertEqual({record.get("selection") for record in result}, {"lexical"})

    def test_dm_retrieval_uses_only_current_speakers_user_namespace(self):
        from memory_extractor import collect_relevant_structured_memories, user_memories_namespace

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            user_memories_namespace(717),
            memory_type="user_preference",
            text="Current DM speaker tracks avionics diagnostics",
            importance=0.9,
            now_iso=now,
        )
        store.upsert_memory(
            user_memories_namespace(111),
            memory_type="user_preference",
            text="Other DM speaker tracks avionics diagnostics",
            importance=1.0,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=None,
            channel_id=777,
            user_id=717,
            query="avionics diagnostics",
            limit=5,
            reserved_global_slots=0,
        )

        texts = [record["text"] for record in result]
        self.assertIn("Current DM speaker tracks avionics diagnostics", texts)
        self.assertNotIn("Other DM speaker tracks avionics diagnostics", texts)

    def test_user_namespace_privacy_holds_when_global_memory_also_matches(self):
        from memory_extractor import (
            collect_relevant_structured_memories,
            global_memories_namespace,
            user_memories_namespace,
        )

        store = self._make_store()
        now = "2026-07-07T12:00:00Z"
        store.upsert_memory(
            user_memories_namespace(111),
            memory_type="user_preference",
            text="Other user private flight sim calibration detail",
            importance=1.0,
            now_iso=now,
        )
        store.upsert_memory(
            global_memories_namespace(),
            memory_type="project_fact",
            text="Shared flight sim calibration project context",
            importance=0.8,
            now_iso=now,
        )

        result = collect_relevant_structured_memories(
            store,
            guild_id=123,
            channel_id=456,
            user_id=717,
            query="flight sim calibration",
            limit=5,
            reserved_global_slots=0,
        )

        texts = [record["text"] for record in result]
        self.assertIn("Shared flight sim calibration project context", texts)
        self.assertNotIn("Other user private flight sim calibration detail", texts)


class MemoryReviewerTests(unittest.TestCase):
    def test_parse_memory_candidates_accepts_strict_json_and_normalizes(self):
        from memory_reviewer import parse_memory_candidates

        candidates = parse_memory_candidates(
            '{"memories":[{"type":"user_preference","scope":"user","user_id":"111","text":"Alice prefers concise debugging replies.","importance":0.8,"confidence":0.9}]}'
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["type"], "user_preference")
        self.assertEqual(candidates[0]["scope"], "user")
        self.assertEqual(candidates[0]["user_id"], 111)

    def test_conflicting_candidate_is_queued_instead_of_applied(self):
        import tempfile
        from memory_extractor import StructuredMemoryStore, user_memories_namespace
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = f"{tmp}/review.jsonl"
            store_path = f"{tmp}/memory_store.json"
            store = StructuredMemoryStore(JsonMemoryStore())
            namespace = user_memories_namespace(111)
            store.upsert_memory(
                namespace,
                memory_type="relationship_note",
                text="For Alice, Leva is their older sister figure",
                now_iso="2026-06-29T00:00:00Z",
            )
            stats = process_memory_candidates(
                [
                    {
                        "type": "relationship_note",
                        "scope": "user",
                        "user_id": 111,
                        "text": "For Alice, Leva is their older sister figure",
                        "importance": 0.8,
                        "confidence": 0.95,
                    }
                ],
                store,
                memory_store_path=store_path,
                review_queue_path=queue_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(stats["dropped"], 1)
            self.assertEqual(stats["queued"], 0)

    def test_user_profile_overlap_is_queued_for_review(self):
        import json
        import tempfile
        from memory_extractor import StructuredMemoryStore
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            profiles_path = f"{tmp}/user_profiles.json"
            queue_path = f"{tmp}/review.jsonl"
            store_path = f"{tmp}/memory_store.json"
            with open(profiles_path, "w", encoding="utf-8") as f:
                json.dump({"148": {"preferred_name": "Leva", "relationship": "older-sister figure to Sash"}}, f)

            stats = process_memory_candidates(
                [
                    {
                        "type": "relationship_note",
                        "scope": "global",
                        "text": "Leva is an older-sister figure to Sash",
                        "importance": 0.8,
                        "confidence": 0.95,
                    }
                ],
                StructuredMemoryStore(JsonMemoryStore()),
                memory_store_path=store_path,
                review_queue_path=queue_path,
                user_profiles_path=profiles_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(stats["queued"], 1)
            with open(queue_path, "r", encoding="utf-8") as f:
                queued = json.loads(f.readline())
            self.assertEqual(queued["status"], "pending")
            kinds = [conflict["kind"] for conflict in queued["conflicts"]]
            self.assertIn("user_profile_overlap", kinds)

    def test_safe_candidate_is_applied(self):
        import tempfile
        from memory_extractor import StructuredMemoryStore, channel_memories_namespace
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            store = StructuredMemoryStore(JsonMemoryStore())
            stats = process_memory_candidates(
                [
                    {
                        "type": "project_fact",
                        "scope": "channel",
                        "text": "We are using OpenAI for neutral memory review",
                        "importance": 0.7,
                        "confidence": 0.92,
                    }
                ],
                store,
                memory_store_path=f"{tmp}/memory_store.json",
                review_queue_path=f"{tmp}/review.jsonl",
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(stats["applied"], 1)
            records = store.list_memories(channel_memories_namespace(guild_id=1, channel_id=2))
            self.assertEqual(records[0]["source"], "api_memory_review")

    def _write_queue_item(self, path: str, *, status: str, namespace: str, text: str) -> None:
        import json

        item = {
            "id": f"test_{status}",
            "status": status,
            "created_at": "2026-06-29T00:00:00Z",
            "candidate": {
                "type": "user_preference",
                "scope": "user",
                "user_id": 111,
                "text": text,
                "importance": 0.8,
                "confidence": 0.95,
            },
            "conflicts": [],
            "namespace": namespace,
            "source": {"test": True},
            "review": {"reviewed_by": None, "reviewed_at": None, "notes": ""},
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    def test_rejected_queue_duplicate_is_dropped(self):
        import tempfile
        from memory_extractor import StructuredMemoryStore, user_memories_namespace
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore

        text = "Alice prefers concise debugging replies."
        namespace = "/".join(user_memories_namespace(111))
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = f"{tmp}/review.jsonl"
            self._write_queue_item(queue_path, status="rejected", namespace=namespace, text=text)
            stats = process_memory_candidates(
                [
                    {
                        "type": "user_preference",
                        "scope": "user",
                        "user_id": 111,
                        "text": text,
                        "importance": 0.8,
                        "confidence": 0.95,
                    }
                ],
                StructuredMemoryStore(JsonMemoryStore()),
                memory_store_path=f"{tmp}/memory_store.json",
                review_queue_path=queue_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(stats["dropped"], 1)
            self.assertEqual(stats["queued"], 0)
            self.assertEqual(stats["applied"], 0)

    def test_applied_and_approved_queue_duplicates_are_dropped(self):
        import tempfile
        from memory_extractor import StructuredMemoryStore, user_memories_namespace
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore

        text = "Alice keeps a pinned note about memory review tooling."
        namespace = "/".join(user_memories_namespace(111))
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = f"{tmp}/review.jsonl"
            self._write_queue_item(queue_path, status="applied", namespace=namespace, text=text)
            self._write_queue_item(
                queue_path,
                status="approved",
                namespace=namespace,
                text="Alice keeps a pinned note about memory review tooling!",
            )

            stats = process_memory_candidates(
                [
                    {
                        "type": "user_preference",
                        "scope": "user",
                        "user_id": 111,
                        "text": text,
                        "importance": 0.8,
                        "confidence": 0.95,
                    }
                ],
                StructuredMemoryStore(JsonMemoryStore()),
                memory_store_path=f"{tmp}/memory_store.json",
                review_queue_path=queue_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(stats["dropped"], 1)
            self.assertEqual(stats["queued"], 0)
            self.assertEqual(stats["applied"], 0)

    def test_near_duplicate_queue_match_is_conservative(self):
        import tempfile
        from memory_extractor import StructuredMemoryStore, user_memories_namespace
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore

        queued_text = "Alice prefers concise debugging replies in this Discord server."
        proposed_near = "Alice prefers concise debugging replies in this Discord channel."
        proposed_distinct = "Alice prefers verbose architecture writeups for backend changes."
        namespace = "/".join(user_memories_namespace(111))
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = f"{tmp}/review.jsonl"
            self._write_queue_item(queue_path, status="pending", namespace=namespace, text=queued_text)

            near_stats = process_memory_candidates(
                [
                    {
                        "type": "user_preference",
                        "scope": "user",
                        "user_id": 111,
                        "text": proposed_near,
                        "importance": 0.8,
                        "confidence": 0.95,
                    }
                ],
                StructuredMemoryStore(JsonMemoryStore()),
                memory_store_path=f"{tmp}/memory_store.json",
                review_queue_path=queue_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )
            distinct_stats = process_memory_candidates(
                [
                    {
                        "type": "user_preference",
                        "scope": "user",
                        "user_id": 111,
                        "text": proposed_distinct,
                        "importance": 0.8,
                        "confidence": 0.95,
                    }
                ],
                StructuredMemoryStore(JsonMemoryStore()),
                memory_store_path=f"{tmp}/memory_store.json",
                review_queue_path=queue_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(near_stats["dropped"], 1)
            self.assertEqual(distinct_stats["applied"], 1)

    def test_queue_duplicate_suppression_is_namespace_scoped(self):
        import tempfile
        from memory_extractor import StructuredMemoryStore, user_memories_namespace
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore

        text = "Prefers concise debugging replies."
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = f"{tmp}/review.jsonl"
            self._write_queue_item(
                queue_path,
                status="rejected",
                namespace="/".join(user_memories_namespace(111)),
                text=text,
            )
            stats = process_memory_candidates(
                [
                    {
                        "type": "user_preference",
                        "scope": "user",
                        "user_id": 222,
                        "text": text,
                        "importance": 0.8,
                        "confidence": 0.95,
                    }
                ],
                StructuredMemoryStore(JsonMemoryStore()),
                memory_store_path=f"{tmp}/memory_store.json",
                review_queue_path=queue_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(stats["applied"], 1)
            self.assertEqual(stats["dropped"], 0)

    def test_same_batch_duplicate_candidates_are_dropped(self):
        import tempfile
        from memory_extractor import StructuredMemoryStore, user_memories_namespace
        from memory_reviewer import process_memory_candidates
        from memory_store import JsonMemoryStore, load_memory_store

        text = "Alice asked for a tested duplicate-memory fix."
        with tempfile.TemporaryDirectory() as tmp:
            queue_path = f"{tmp}/review.jsonl"
            store_path = f"{tmp}/memory_store.json"
            stats = process_memory_candidates(
                [
                    {
                        "type": "user_preference",
                        "scope": "user",
                        "user_id": 111,
                        "text": text,
                        "importance": 0.8,
                        "confidence": 0.95,
                    },
                    {
                        "type": "user_preference",
                        "scope": "user",
                        "user_id": 111,
                        "text": "Alice asked for a tested duplicate memory fix.",
                        "importance": 0.8,
                        "confidence": 0.95,
                    },
                ],
                StructuredMemoryStore(JsonMemoryStore()),
                memory_store_path=store_path,
                review_queue_path=queue_path,
                guild_id=1,
                channel_id=2,
                source={"test": True},
            )

            self.assertEqual(stats["applied"], 1)
            self.assertEqual(stats["dropped"], 1)
            self.assertEqual(stats["queued"], 0)
            store = StructuredMemoryStore(JsonMemoryStore())
            store.store = load_memory_store(store_path)
            records = store.list_memories(user_memories_namespace(111))
            self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
