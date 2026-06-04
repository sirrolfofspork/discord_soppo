import os
import unittest
from unittest.mock import patch


BASE_ENV = {
    "DISCORD_BOT_TOKEN": "dummy-token",
    "LLM_BACKEND": "ollama",
}


class OutputSanitizerTests(unittest.TestCase):
    def test_strips_repeated_leading_speaker_labels(self):
        from bot import sanitize_llm_reply_for_discord

        self.assertEqual(
            sanitize_llm_reply_for_discord("SOPPO: Soppo: M4 SOPMOD II: GYAHAHA, target locked!"),
            "GYAHAHA, target locked!",
        )
        self.assertEqual(
            sanitize_llm_reply_for_discord("**Soppo:** SOPPO: GYAHAHA, target locked!"),
            "GYAHAHA, target locked!",
        )

    def test_preserves_non_leading_mentions_of_name(self):
        from bot import sanitize_llm_reply_for_discord

        self.assertEqual(
            sanitize_llm_reply_for_discord("GYAHAHA! Soppo has the archive locked."),
            "GYAHAHA! Soppo has the archive locked.",
        )


class CanonicalAppearancePromptTests(unittest.TestCase):
    def test_system_prompt_rejects_fox_trait_drift(self):
        from prompts import build_system_prompt

        prompt = build_system_prompt().lower()

        self.assertIn("does not have fox ears", prompt)
        self.assertIn("does not have a fox tail", prompt)
        self.assertIn("temporary jokes", prompt)
        self.assertIn("permanent body traits", prompt)


class GuildStructuredMemoryTests(unittest.TestCase):
    def test_guild_namespace_is_distinct_from_channel_namespace(self):
        from memory_extractor import guild_memories_namespace

        self.assertEqual(guild_memories_namespace(123), ("discord", "guild", "123", "memories"))
        self.assertEqual(guild_memories_namespace(None), ("discord", "dm", "memories"))

    def test_collects_user_guild_channel_and_global_memories_with_cap(self):
        from memory_extractor import (
            StructuredMemoryStore,
            channel_memories_namespace,
            collect_relevant_structured_memories,
            global_memories_namespace,
            guild_memories_namespace,
            user_memories_namespace,
        )
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        memories = StructuredMemoryStore(store)
        now = "2026-05-29T12:00:00Z"
        memories.upsert_memory(user_memories_namespace(9), memory_type="user_preference", text="Alice prefers short replies", importance=0.9, now_iso=now)
        memories.upsert_memory(guild_memories_namespace(123), memory_type="server_fact", text="The guild uses a bot-lab channel", importance=0.8, now_iso=now)
        memories.upsert_memory(channel_memories_namespace(guild_id=123, channel_id=456), memory_type="project_fact", text="Channel 456 tests LM Studio", importance=0.7, now_iso=now)
        memories.upsert_memory(global_memories_namespace(), memory_type="character_note", text="SOPPO should avoid stale labels", importance=0.6, now_iso=now)
        memories.upsert_memory(channel_memories_namespace(guild_id=123, channel_id=999), memory_type="project_fact", text="Other channel private detail", importance=1.0, now_iso=now)

        result = collect_relevant_structured_memories(
            memories,
            guild_id=123,
            channel_id=456,
            user_id=9,
            query="short bot-lab LM Studio labels",
            limit=4,
        )
        texts = [record["text"] for record in result]

        self.assertEqual(len(result), 4)
        self.assertIn("Alice prefers short replies", texts)
        self.assertIn("The guild uses a bot-lab channel", texts)
        self.assertIn("Channel 456 tests LM Studio", texts)
        self.assertIn("SOPPO should avoid stale labels", texts)
        self.assertNotIn("Other channel private detail", texts)


class OpenAITimeoutConfigTests(unittest.TestCase):
    def test_openai_timeout_seconds_is_configurable(self):
        from config import load_config

        env = {
            **BASE_ENV,
            "LLM_BACKEND": "openai",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_TIMEOUT_SECONDS": "37.5",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.openai_timeout_seconds, 37.5)


if __name__ == "__main__":
    unittest.main()
