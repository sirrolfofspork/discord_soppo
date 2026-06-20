from collections import deque
import os
import unittest
from unittest.mock import patch


BASE_ENV = {
    "DISCORD_BOT_TOKEN": "dummy-token",
    "LLM_BACKEND": "ollama",
}


class ChannelSummaryMemoryTests(unittest.TestCase):
    def test_summary_rollover_summarizes_oldest_batch_and_removes_it(self):
        from memory import apply_summary_rollover

        history = deque(
            [
                {"role": "user", "content": "[Alice]: first old detail"},
                {"role": "assistant", "content": "SOPPO remembers the first detail"},
                {"role": "user", "content": "[Bob]: recent detail"},
                {"role": "assistant", "content": "recent reply"},
                {"role": "user", "content": "[Alice]: current question"},
            ]
        )

        summary, summarized = apply_summary_rollover(
            history,
            current_summary="",
            threshold=3,
            batch_size=2,
            max_summary_chars=1000,
        )

        self.assertEqual(summarized, 2)
        self.assertIn("[Alice]: first old detail", summary)
        self.assertIn("SOPPO remembers the first detail", summary)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["content"], "[Bob]: recent detail")
        self.assertEqual(history[-1]["content"], "[Alice]: current question")

    def test_summary_truncation_keeps_newest_summary_content(self):
        from memory import merge_channel_summary

        old_summary = "- very old detail " * 40
        turns = [{"role": "user", "content": "[Alice]: newest important detail about the plan"}]

        summary = merge_channel_summary(
            old_summary,
            turns,
            max_chars=120,
        )

        self.assertLessEqual(len(summary), 120)
        self.assertIn("newest important detail", summary)

    def test_channel_summary_block_formatting(self):
        from memory import build_channel_summary_block

        block = build_channel_summary_block("- [Alice]: likes G11")

        self.assertIn("[Channel neutral summary]", block)
        self.assertIn("- [Alice]: likes G11", block)
        self.assertIn("Recent raw messages below are newer", block)

    def test_config_loads_summary_thresholds(self):
        from config import load_config

        env = {
            **BASE_ENV,
            "MAX_CONTEXT_MESSAGES": "20",
            "MAX_CONTEXT_MESSAGES_BEFORE_SUMMARY": "12",
            "SUMMARY_BATCH_SIZE": "5",
            "MAX_CHANNEL_SUMMARY_CHARS": "900",
            "MEMORY_STORE_PATH": "local_memory.json",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.max_context_messages_before_summary, 12)
        self.assertEqual(config.summary_batch_size, 5)
        self.assertEqual(config.max_channel_summary_chars, 900)
        self.assertEqual(config.memory_store_path, "local_memory.json")

    def test_channel_summary_memory_persists_via_memory_store_namespace(self):
        from memory import ChannelSummaryMemory
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        memory = ChannelSummaryMemory(store)
        memory.set_summary(guild_id=123, channel_id=456, summary="- [Alice]: saved detail")

        self.assertEqual(memory.get_summary(guild_id=123, channel_id=456), "- [Alice]: saved detail")
        self.assertEqual(
            store.get_memory(("discord", "guild", "123", "channel", "456", "summary"), "current"),
            {"text": "- [Alice]: saved detail"},
        )

    def test_channel_summary_metadata_merges_without_overwriting_text(self):
        from memory import ChannelSummaryMemory
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        memory = ChannelSummaryMemory(store)
        memory.set_summary(guild_id=123, channel_id=456, summary="- [Alice]: saved detail")
        memory.update_summary_metadata(
            guild_id=123,
            channel_id=456,
            messages_since_regen=2,
            last_regen_status="waiting_threshold",
            text="should be ignored",
        )

        record = store.get_memory(("discord", "guild", "123", "channel", "456", "summary"), "current")
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["text"], "- [Alice]: saved detail")
        self.assertEqual(record["messages_since_regen"], 2)
        self.assertEqual(record["last_regen_status"], "waiting_threshold")

    def test_channel_summary_memory_uses_dm_namespace_without_guild(self):
        from memory import ChannelSummaryMemory
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        memory = ChannelSummaryMemory(store)
        memory.set_summary(guild_id=None, channel_id=456, summary="- DM detail")

        self.assertEqual(
            store.get_memory(("discord", "dm", "channel", "456", "summary"), "current"),
            {"text": "- DM detail"},
        )


class PromptAssemblyOrderingTests(unittest.TestCase):
    def test_prompt_order_places_summary_between_speaker_and_lore(self):
        from bot import build_prompt_messages

        messages = build_prompt_messages(
            system_prompt="SYSTEM",
            speaker_context="SPEAKER",
            channel_summary_block="SUMMARY",
            structured_memory_block="STRUCTURED",
            lore_block="LORE",
            returning_hint="FOLLOWUP",
            history=[
                {"role": "user", "content": "old recent"},
                {"role": "user", "content": "current message"},
            ],
        )

        self.assertEqual(
            [m["content"] for m in messages],
            [
                "SYSTEM",
                "SPEAKER",
                "SUMMARY",
                "STRUCTURED",
                "LORE",
                "FOLLOWUP",
                "old recent",
                "[Newest live Discord message — answer this message directly now]\ncurrent message",
            ],
        )
        self.assertEqual([m["role"] for m in messages[:6]], ["system"] * 6)
        self.assertEqual(messages[-1]["role"], "user")


if __name__ == "__main__":
    unittest.main()
