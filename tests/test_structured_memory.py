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
        self.assertIn("Use only when relevant", block)


if __name__ == "__main__":
    unittest.main()
