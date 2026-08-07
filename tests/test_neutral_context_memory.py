import os
import tempfile
import unittest
import asyncio
from collections import deque
from unittest.mock import patch


BASE_ENV = {
    "DISCORD_BOT_TOKEN": "dummy-token",
    "LLM_BACKEND": "ollama",
}


def make_config(**overrides):
    from config import Config

    values = dict(
        discord_bot_token="dummy",
        llm_backend="ollama",
        ollama_model="model",
        ollama_url="http://localhost:11434",
        openai_api_key="",
        openai_model="gpt",
        openai_timeout_seconds=120.0,
        lmstudio_base_url="http://localhost:1234/v1",
        lmstudio_api_key="not-needed",
        lmstudio_model="local",
        discord_allowed_channel_ids=(),
        discord_channel_name="general",
        respond_to_other_bots=False,
        bot_author_cooldown_seconds=60.0,
        spontaneous_reply_chance=0.0,
        reply_cooldown_seconds=0.0,
        max_context_messages=20,
        max_context_messages_before_summary=16,
        summary_batch_size=6,
        max_channel_summary_chars=1200,
        memory_store_path=":memory:",
        max_prompt_chars=8000,
        temperature=0.9,
        top_p=0.9,
        max_tokens=160,
        bot_name_aliases=(),
        discord_reply_soft_limit=500,
        discord_reply_hard_limit=1800,
        returning_user_threshold_seconds=43200.0,
        user_greeting_cooldown_seconds=86400.0,
        channel_greeting_cooldown_seconds=14400.0,
        returning_user_greeting_chance=0.2,
        inferred_followup_window_seconds=180.0,
        recent_raw_turns=3,
        summary_regen_message_count=2,
        summary_regen_min_seconds=0.0,
        max_neutral_summary_chars=1800,
        summary_model_mode="neutral",
    )
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]


class NeutralSummaryConfigTests(unittest.TestCase):
    def test_config_loads_neutral_summary_defaults_and_overrides(self):
        from config import load_config

        env = {
            **BASE_ENV,
            "RECENT_RAW_TURNS": "2",
            "SUMMARY_REGEN_MESSAGE_COUNT": "11",
            "SUMMARY_REGEN_MIN_SECONDS": "301",
            "MAX_NEUTRAL_SUMMARY_CHARS": "1700",
            "SUMMARY_MODEL_MODE": "neutral",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.recent_raw_turns, 2)
        self.assertEqual(config.summary_regen_message_count, 11)
        self.assertEqual(config.summary_regen_min_seconds, 301.0)
        self.assertEqual(config.max_neutral_summary_chars, 1700)
        self.assertEqual(config.summary_model_mode, "neutral")

    def test_config_loads_api_background_memory_options(self):
        from config import load_config

        env = {
            **BASE_ENV,
            "OPENAI_API_KEY": "test-openai-key",
            "OPENAI_MODEL": "gpt-main",
            "SUMMARY_LLM_BACKEND": "openai",
            "SUMMARY_OPENAI_MODEL": "gpt-summary",
            "MEMORY_REVIEW_ENABLED": "true",
            "MEMORY_REVIEW_LLM_BACKEND": "openai",
            "MEMORY_REVIEW_OPENAI_MODEL": "gpt-memory",
            "MEMORY_REVIEW_QUEUE_PATH": "custom_review.jsonl",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.summary_llm_backend, "openai")
        self.assertEqual(config.summary_openai_model, "gpt-summary")
        self.assertEqual(config.summary_openai_api_key, "test-openai-key")
        self.assertTrue(config.memory_review_enabled)
        self.assertEqual(config.memory_review_llm_backend, "openai")
        self.assertEqual(config.memory_review_openai_model, "gpt-memory")
        self.assertEqual(config.memory_review_openai_api_key, "test-openai-key")
        self.assertEqual(config.memory_review_queue_path, "custom_review.jsonl")


class NeutralSummaryPromptTests(unittest.TestCase):
    def test_neutral_summarizer_prompt_excludes_soppo_persona_text(self):
        from memory import build_neutral_summary_messages

        messages = build_neutral_summary_messages(
            current_summary="- prior factual point",
            new_turns=[{"role": "user", "content": "[Alice]: ROAR moved today"}],
            max_summary_chars=1800,
        )
        joined = "\n".join(m["content"] for m in messages).lower()

        self.assertIn("neutral", joined)
        self.assertIn("running jokes clearly labeled as jokes", joined)
        self.assertIn("external scene context only", joined)
        self.assertIn("do not summarize temporary roleplay facts", joined)
        self.assertIn("must not modify soppo identity", joined)
        self.assertNotIn("girls' frontline", joined)
        self.assertNotIn("gya", joined)
        self.assertNotIn("mischievous", joined)

    def test_neutral_summarizer_prompt_requires_exact_section_headings(self):
        from memory import (
            NEUTRAL_SUMMARY_SECTION_CURRENT,
            NEUTRAL_SUMMARY_SECTION_DURABLE,
            NEUTRAL_SUMMARY_SECTION_OPEN_LOOPS,
            NEUTRAL_SUMMARY_SECTION_PREVIOUS,
            build_neutral_summary_messages,
        )

        messages = build_neutral_summary_messages(
            current_summary="Current topic:\n- old thread",
            new_turns=[{"role": "user", "content": "[Bob]: new question"}],
            max_summary_chars=1800,
        )
        joined = "\n".join(m["content"] for m in messages)

        for heading in (
            NEUTRAL_SUMMARY_SECTION_CURRENT,
            NEUTRAL_SUMMARY_SECTION_PREVIOUS,
            NEUTRAL_SUMMARY_SECTION_OPEN_LOOPS,
            NEUTRAL_SUMMARY_SECTION_DURABLE,
        ):
            self.assertIn(heading, joined)
        self.assertIn("exact section headings", joined.lower())
        self.assertIn("migrate it into the sectioned format", joined.lower())
        self.assertIn("move the old current topic here", joined.lower())

    def test_channel_summary_block_tells_model_not_to_answer_every_summary_bullet(self):
        from memory import build_channel_summary_block

        block = build_channel_summary_block("- Old topic about robot bodies")

        self.assertIn("background continuity", block)
        self.assertIn("Do not answer, continue, or re-raise every bullet", block)
        self.assertIn("newest live message changes topic", block)

    def test_channel_summary_block_preserves_sectioned_boundaries(self):
        from memory import (
            NEUTRAL_SUMMARY_SECTION_CURRENT,
            NEUTRAL_SUMMARY_SECTION_DURABLE,
            NEUTRAL_SUMMARY_SECTION_OPEN_LOOPS,
            NEUTRAL_SUMMARY_SECTION_PREVIOUS,
            build_channel_summary_block,
        )

        summary = "\n".join(
            [
                NEUTRAL_SUMMARY_SECTION_CURRENT,
                "- [Alice]: asking about lunch plans",
                NEUTRAL_SUMMARY_SECTION_PREVIOUS,
                "- [Bob]: earlier rant about robot bodies",
                NEUTRAL_SUMMARY_SECTION_OPEN_LOOPS,
                "- whether Alice still wants pizza",
                NEUTRAL_SUMMARY_SECTION_DURABLE,
                "- Alice prefers short replies",
            ]
        )
        block = build_channel_summary_block(summary)

        self.assertIn(NEUTRAL_SUMMARY_SECTION_CURRENT, block)
        self.assertIn(NEUTRAL_SUMMARY_SECTION_PREVIOUS, block)
        self.assertIn(NEUTRAL_SUMMARY_SECTION_OPEN_LOOPS, block)
        self.assertIn(NEUTRAL_SUMMARY_SECTION_DURABLE, block)
        self.assertIn("Active thread", block)
        self.assertIn("Closed background", block)
        self.assertIn("- [Bob]: earlier rant about robot bodies", block)

    def test_channel_summary_block_marks_closed_topics_as_background_on_topic_change(self):
        from memory import (
            NEUTRAL_SUMMARY_SECTION_CURRENT,
            NEUTRAL_SUMMARY_SECTION_DURABLE,
            NEUTRAL_SUMMARY_SECTION_OPEN_LOOPS,
            NEUTRAL_SUMMARY_SECTION_PREVIOUS,
            build_channel_summary_block,
        )

        summary = "\n".join(
            [
                NEUTRAL_SUMMARY_SECTION_CURRENT,
                "- [Alice]: asking about lunch plans",
                NEUTRAL_SUMMARY_SECTION_PREVIOUS,
                "- heated argument about robot bodies",
                NEUTRAL_SUMMARY_SECTION_OPEN_LOOPS,
                "- (none)",
                NEUTRAL_SUMMARY_SECTION_DURABLE,
                "- (none)",
            ]
        )
        block = build_channel_summary_block(summary)

        self.assertIn("Previous/closed topics as closed background only", block)
        self.assertIn("ignore Previous/closed topics and stale Current topic details", block)
        self.assertIn("not prompts to continue old threads", block)
        self.assertIn("heated argument about robot bodies", block)

    def test_unsectioned_summary_block_remains_backward_compatible(self):
        from memory import annotate_sectioned_neutral_summary, build_channel_summary_block, is_sectioned_neutral_summary

        legacy = "- Alice asked about robots; unresolved whether repairs are done."
        self.assertFalse(is_sectioned_neutral_summary(legacy))
        self.assertEqual(annotate_sectioned_neutral_summary(legacy), legacy)

        block = build_channel_summary_block(legacy)
        self.assertIn(legacy, block)
        self.assertIn("ignore stale summary details", block)
        self.assertNotIn("Previous/closed topics as closed background only", block)

    def test_build_prompt_messages_order_and_recent_raw_limit(self):
        from bot import build_prompt_messages

        history = deque(
            [
                {"role": "user", "content": "raw-1"},
                {"role": "assistant", "content": "raw-2"},
                {"role": "user", "content": "raw-3"},
                {"role": "assistant", "content": "raw-4"},
            ]
        )

        messages = build_prompt_messages(
            system_prompt="1 CORE",
            speaker_context="2 SPEAKER",
            guild_memory_block="3 GUILD",
            channel_summary_block="4 SUMMARY",
            channel_memory_block="5 CHANNEL",
            lore_block="6 LORE",
            returning_hint="7 HINT",
            history=history,
            recent_raw_turns=3,
        )

        self.assertEqual(
            [m["content"] for m in messages],
            [
                "1 CORE",
                "2 SPEAKER",
                "3 GUILD",
                "4 SUMMARY",
                "5 CHANNEL",
                "6 LORE",
                "7 HINT",
                "raw-2",
                "raw-3",
                "raw-4",
            ],
        )
        self.assertEqual(messages[-1]["role"], "assistant")
        self.assertNotIn("Newest live Discord message", messages[-1]["content"])
        self.assertNotIn("Newest live Discord message", messages[-2]["content"])

    def test_build_prompt_messages_marks_latest_user_turn_as_live_message(self):
        from bot import build_prompt_messages
        from prompts import build_user_message_wrapper

        current_turn = build_user_message_wrapper("Alice", "current question")
        history = deque(
            [
                {"role": "user", "content": "old user"},
                {"role": "assistant", "content": "old reply"},
                {"role": "user", "content": current_turn},
            ]
        )

        messages = build_prompt_messages(
            system_prompt="CORE",
            channel_summary_block="SUMMARY",
            history=history,
            recent_raw_turns=3,
        )

        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(
            messages[-1]["content"],
            f"[Newest live Discord message — answer this message directly now]\n{current_turn}",
        )
        self.assertNotIn("Newest live Discord message", messages[-3]["content"])


class NeutralSummaryRegenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_regeneration_waits_for_threshold_count(self):
        from bot import SoppoBot
        from config import Config

        config = Config(
            discord_bot_token="dummy",
            llm_backend="ollama",
            ollama_model="model",
            ollama_url="http://localhost:11434",
            openai_api_key="",
            openai_model="gpt",
            openai_timeout_seconds=120.0,
            lmstudio_base_url="http://localhost:1234/v1",
            lmstudio_api_key="not-needed",
            lmstudio_model="local",
            discord_allowed_channel_ids=(),
            discord_channel_name="general",
            respond_to_other_bots=False,
            bot_author_cooldown_seconds=60.0,
            spontaneous_reply_chance=0.0,
            reply_cooldown_seconds=0.0,
            max_context_messages=20,
            max_context_messages_before_summary=16,
            summary_batch_size=6,
            max_channel_summary_chars=1200,
            memory_store_path=":memory:",
            max_prompt_chars=8000,
            temperature=0.9,
            top_p=0.9,
            max_tokens=160,
            bot_name_aliases=(),
            discord_reply_soft_limit=500,
            discord_reply_hard_limit=1800,
            returning_user_threshold_seconds=43200.0,
            user_greeting_cooldown_seconds=86400.0,
            channel_greeting_cooldown_seconds=14400.0,
            returning_user_greeting_chance=0.2,
            inferred_followup_window_seconds=180.0,
            recent_raw_turns=3,
            summary_regen_message_count=3,
            summary_regen_min_seconds=0.0,
            max_neutral_summary_chars=1800,
            summary_model_mode="neutral",
        )
        bot = SoppoBot(config)
        with patch("bot.generate_reply", autospec=True) as mock_generate:
            mock_generate.return_value = "- neutral summary"
            bot._record_turn_for_neutral_summary(1, {"role": "user", "content": "one"})
            bot._record_turn_for_neutral_summary(1, {"role": "user", "content": "two"})
            changed = await bot._maybe_regenerate_neutral_summary(channel_id=1, guild_id=None, now_wall=100.0)

        self.assertFalse(changed)
        mock_generate.assert_not_called()
        record = bot._channel_summary_memory.get_summary_record(guild_id=None, channel_id=1)
        self.assertEqual(record["messages_since_regen"], 2)
        self.assertEqual(record["pending_turn_count"], 2)
        self.assertEqual(record["last_seen_message_time"], 100.0)
        self.assertEqual(record["last_regen_status"], "waiting_threshold")

    async def test_summary_regeneration_respects_cooldown(self):
        from bot import SoppoBot
        from config import Config

        config = Config(
            discord_bot_token="dummy",
            llm_backend="ollama",
            ollama_model="model",
            ollama_url="http://localhost:11434",
            openai_api_key="",
            openai_model="gpt",
            openai_timeout_seconds=120.0,
            lmstudio_base_url="http://localhost:1234/v1",
            lmstudio_api_key="not-needed",
            lmstudio_model="local",
            discord_allowed_channel_ids=(),
            discord_channel_name="general",
            respond_to_other_bots=False,
            bot_author_cooldown_seconds=60.0,
            spontaneous_reply_chance=0.0,
            reply_cooldown_seconds=0.0,
            max_context_messages=20,
            max_context_messages_before_summary=16,
            summary_batch_size=6,
            max_channel_summary_chars=1200,
            memory_store_path=":memory:",
            max_prompt_chars=8000,
            temperature=0.9,
            top_p=0.9,
            max_tokens=160,
            bot_name_aliases=(),
            discord_reply_soft_limit=500,
            discord_reply_hard_limit=1800,
            returning_user_threshold_seconds=43200.0,
            user_greeting_cooldown_seconds=86400.0,
            channel_greeting_cooldown_seconds=14400.0,
            returning_user_greeting_chance=0.2,
            inferred_followup_window_seconds=180.0,
            recent_raw_turns=3,
            summary_regen_message_count=2,
            summary_regen_min_seconds=300.0,
            max_neutral_summary_chars=1800,
            summary_model_mode="neutral",
        )
        bot = SoppoBot(config)
        bot._summary_last_regen_wall[1] = 50.0
        bot._record_turn_for_neutral_summary(1, {"role": "user", "content": "one"})
        bot._record_turn_for_neutral_summary(1, {"role": "user", "content": "two"})
        with patch("bot.generate_reply", autospec=True) as mock_generate:
            mock_generate.return_value = "- neutral summary"
            changed = await bot._maybe_regenerate_neutral_summary(channel_id=1, guild_id=None, now_wall=100.0)

        self.assertFalse(changed)
        mock_generate.assert_not_called()
        record = bot._channel_summary_memory.get_summary_record(guild_id=None, channel_id=1)
        self.assertEqual(record["last_regen_status"], "cooldown")
        self.assertEqual(record["messages_since_regen"], 2)
        self.assertIsInstance(record["cooldown_remaining_seconds"], float)

    async def test_summary_regeneration_stores_neutral_summary_record(self):
        from bot import SoppoBot
        from config import Config

        with tempfile.TemporaryDirectory() as tmpdir:
            config = Config(
                discord_bot_token="dummy",
                llm_backend="ollama",
                ollama_model="model",
                ollama_url="http://localhost:11434",
                openai_api_key="",
                openai_model="gpt",
                openai_timeout_seconds=120.0,
                lmstudio_base_url="http://localhost:1234/v1",
                lmstudio_api_key="not-needed",
                lmstudio_model="local",
                discord_allowed_channel_ids=(),
                discord_channel_name="general",
                respond_to_other_bots=False,
                bot_author_cooldown_seconds=60.0,
                spontaneous_reply_chance=0.0,
                reply_cooldown_seconds=0.0,
                max_context_messages=20,
                max_context_messages_before_summary=16,
                summary_batch_size=6,
                max_channel_summary_chars=1200,
                memory_store_path=os.path.join(tmpdir, "memory_store.json"),
                max_prompt_chars=8000,
                temperature=0.9,
                top_p=0.9,
                max_tokens=160,
                bot_name_aliases=(),
                discord_reply_soft_limit=500,
                discord_reply_hard_limit=1800,
                returning_user_threshold_seconds=43200.0,
                user_greeting_cooldown_seconds=86400.0,
                channel_greeting_cooldown_seconds=14400.0,
                returning_user_greeting_chance=0.2,
                inferred_followup_window_seconds=180.0,
                recent_raw_turns=3,
                summary_regen_message_count=2,
                summary_regen_min_seconds=0.0,
                max_neutral_summary_chars=1800,
                summary_model_mode="neutral",
            )
            bot = SoppoBot(config)
            bot._record_turn_for_neutral_summary(99, {"role": "user", "content": "[Alice]: first"})
            bot._record_turn_for_neutral_summary(99, {"role": "assistant", "content": "reply"})
            with patch("bot.generate_reply", autospec=True) as mock_generate:
                mock_generate.return_value = "- Alice asked about first; SOPPO replied."
                changed = await bot._maybe_regenerate_neutral_summary(channel_id=99, guild_id=123, now_wall=100.0)

            self.assertTrue(changed)
            record = bot._channel_summary_memory.get_summary_record(guild_id=123, channel_id=99)
            self.assertEqual(record["text"], "- Alice asked about first; SOPPO replied.")
            self.assertEqual(record["mode"], "neutral")
            self.assertEqual(record["messages_since_regen"], 0)
            self.assertEqual(record["pending_turn_count"], 0)
            self.assertEqual(record["last_regen_status"], "success")
            self.assertEqual(record["last_regen_error"], "")
            self.assertEqual(bot._summary_pending_turns[99], [])

    async def test_summary_regeneration_skips_when_same_channel_summary_already_in_progress(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config(summary_regen_message_count=2))
        bot._record_turn_for_neutral_summary(7, {"role": "user", "content": "one"})
        bot._record_turn_for_neutral_summary(7, {"role": "assistant", "content": "two"})
        bot._summary_in_progress.add(7)

        with patch("bot.generate_reply", autospec=True) as mock_generate:
            mock_generate.return_value = "- should not run"
            changed = await bot._maybe_regenerate_neutral_summary(channel_id=7, guild_id=None, now_wall=100.0)

        self.assertFalse(changed)
        mock_generate.assert_not_called()
        self.assertEqual(bot._summary_messages_since_regen[7], 2)

    async def test_lmstudio_summary_generation_waits_for_shared_generation_lock(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config(llm_backend="lmstudio", summary_regen_message_count=2))
        bot._record_turn_for_neutral_summary(8, {"role": "user", "content": "one"})
        bot._record_turn_for_neutral_summary(8, {"role": "assistant", "content": "two"})
        await bot._generation_lock.acquire()
        try:
            with patch("bot.generate_reply", autospec=True) as mock_generate:
                mock_generate.return_value = "- summary after lock"
                task = asyncio.create_task(
                    bot._maybe_regenerate_neutral_summary(channel_id=8, guild_id=None, now_wall=100.0)
                )
                await asyncio.sleep(0)
                mock_generate.assert_not_called()
                self.assertFalse(task.done())
                bot._generation_lock.release()
                changed = await task
        finally:
            if bot._generation_lock.locked():
                bot._generation_lock.release()

        self.assertTrue(changed)
        mock_generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
