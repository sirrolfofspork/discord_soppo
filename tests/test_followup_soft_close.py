import unittest


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
        bot_name_aliases=("Soppo", "Sash"),
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


class IdentityRecoveryTests(unittest.TestCase):
    def test_identity_recovery_detects_direct_identity_probes(self):
        from bot import message_needs_identity_recovery

        positives = [
            "Sash, who are you?",
            "identity check",
            "Are you Leva?",
            "GYAHAHA!! But seriously, you're not Leva, right?",
            "What's the deal with Leva anyway?",
        ]
        for phrase in positives:
            with self.subTest(phrase=phrase):
                self.assertTrue(message_needs_identity_recovery(phrase))

    def test_identity_reset_context_keeps_llm_in_loop_after_cleanup(self):
        from bot import build_identity_reset_context

        context = build_identity_reset_context(
            speaker_profile={
                "preferred_name": "Leva",
                "username": "Leva_v1#4378",
                "pronouns": "she/her",
                "relationship": "AI companion of SKK and Sash; older-sister figure to Sash",
            }
        )

        self.assertIn("[Identity reset mode]", context)
        self.assertIn("rolling channel summary were purged", context)
        self.assertIn("Answer using only the core SOPPO/Sash identity prompt", context)
        self.assertIn("If Leva is relevant, identify Leva as separate from SOPPO", context)
        self.assertIn("older-sister figure", context)

    def test_identity_reset_purges_recent_context_without_disabling_llm(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        hist = bot._history_for(10)
        hist.append({"role": "user", "content": "old roleplay contamination"})
        bot._summary_pending_turns[10] = [{"role": "assistant", "content": "old reply"}]
        bot._summary_messages_since_regen[10] = 4
        bot._last_bot_text[10] = "Wait, am I Leva?"
        bot._channel_summary_memory.set_neutral_summary(
            guild_id=20,
            channel_id=10,
            summary="Old Leva identity confusion summary",
            last_regen_wall=1.0,
            messages_since_regen=4,
        )

        bot._purge_context_for_identity_reset(channel_id=10, guild_id=20, now_wall=100.0)

        self.assertEqual(list(bot._history_for(10)), [])
        self.assertEqual(bot._summary_pending_turns[10], [])
        self.assertEqual(bot._summary_messages_since_regen[10], 0)
        self.assertNotIn(10, bot._last_bot_text)
        record = bot._channel_summary_memory.get_summary_record(guild_id=20, channel_id=10)
        self.assertEqual(record["text"], "")
        self.assertEqual(record["last_regen_status"], "identity_reset_purged")


class SoftCloseDetectionTests(unittest.TestCase):
    def test_soft_close_phrases_are_detected(self):
        from bot import message_is_soft_close

        positives = [
            "that's all",
            "thanks, that's all.",
            "Sash, stand down",
            "Soppo go quiet",
            "stop replying, Soppo",
        ]
        for phrase in positives:
            with self.subTest(phrase=phrase):
                self.assertTrue(message_is_soft_close(phrase))

    def test_normal_messages_are_not_soft_closes(self):
        from bot import message_is_soft_close

        negatives = [
            "stop doing that and explain why",
            "all good ideas should go in the doc",
            "thanks for checking the sensor log",
            "quietly calculate the route",
        ]
        for phrase in negatives:
            with self.subTest(phrase=phrase):
                self.assertFalse(message_is_soft_close(phrase))


class SleepCommandDetectionTests(unittest.TestCase):
    def test_sleep_phrases_are_detected(self):
        from bot import message_is_sleep_command

        positives = [
            "Soppo sleep",
            "Soppo, go to sleep.",
            "Sash stand down",
            "!soppo stop replying",
            "go quiet, Soppo",
            "stop talking Sash",
        ]
        for phrase in positives:
            with self.subTest(phrase=phrase):
                self.assertTrue(message_is_sleep_command(phrase))

    def test_sleep_detection_requires_soppo_or_sash_target(self):
        from bot import message_is_sleep_command

        negatives = [
            "I need sleep",
            "the channel should go quiet for a minute",
            "Shadow stand down",
            "please stop talking about that and explain",
        ]
        for phrase in negatives:
            with self.subTest(phrase=phrase):
                self.assertFalse(message_is_sleep_command(phrase))

    def test_wake_phrases_are_detected(self):
        from bot import message_is_wake_command

        positives = [
            "Soppo wake up",
            "Sash, resume",
            "!soppo wake",
            "wake up Soppo",
            "come back, Sash",
        ]
        for phrase in positives:
            with self.subTest(phrase=phrase):
                self.assertTrue(message_is_wake_command(phrase))

    def test_wake_detection_requires_soppo_or_sash_target(self):
        from bot import message_is_wake_command

        negatives = [
            "I need to wake up",
            "wake up everyone",
            "Shadow resume",
            "online status looks good",
        ]
        for phrase in negatives:
            with self.subTest(phrase=phrase):
                self.assertFalse(message_is_wake_command(phrase))


class ReplyCoalescingTests(unittest.TestCase):
    def test_reply_queue_priority_prefers_identity_then_direct_then_followup(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())

        self.assertEqual(bot._reply_queue_priority("name_alias"), 2)
        self.assertEqual(bot._reply_queue_priority("inferred_followup"), 1)
        self.assertEqual(bot._reply_queue_priority("spontaneous"), 0)
        self.assertEqual(bot._reply_queue_priority("name_alias", identity_reset=True), 3)

    def test_pending_reply_coalescing_keeps_latest_equal_or_higher_priority(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        followup_1 = object()
        followup_2 = object()
        direct = object()
        later_followup = object()

        self.assertTrue(
            bot._store_pending_reply_message(
                channel_id=10,
                message=followup_1,  # type: ignore[arg-type]
                reason="inferred_followup",
            )
        )
        self.assertTrue(
            bot._store_pending_reply_message(
                channel_id=10,
                message=followup_2,  # type: ignore[arg-type]
                reason="inferred_followup",
            )
        )
        self.assertIs(bot._pending_reply_messages[10]["message"], followup_2)

        self.assertTrue(
            bot._store_pending_reply_message(
                channel_id=10,
                message=direct,  # type: ignore[arg-type]
                reason="name_alias",
            )
        )
        self.assertIs(bot._pending_reply_messages[10]["message"], direct)

        self.assertFalse(
            bot._store_pending_reply_message(
                channel_id=10,
                message=later_followup,  # type: ignore[arg-type]
                reason="inferred_followup",
            )
        )
        self.assertIs(bot._pending_reply_messages[10]["message"], direct)

    def test_sleep_clears_pending_reply_for_channel(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        bot._store_pending_reply_message(
            channel_id=10,
            message=object(),  # type: ignore[arg-type]
            reason="name_alias",
        )

        bot._put_channel_to_sleep(10)

        self.assertNotIn(10, bot._pending_reply_messages)


class InferredFollowupWindowTests(unittest.TestCase):
    def test_clear_inferred_followup_window_removes_only_target_user(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        bot._refresh_inferred_followup_window(channel_id=10, user_id=111, now_wall=1000.0)
        bot._refresh_inferred_followup_window(channel_id=10, user_id=222, now_wall=1000.0)

        self.assertTrue(bot._inferred_followup_is_active(10, 111, 1001.0))
        bot._clear_inferred_followup_window(10, 111)

        self.assertFalse(bot._inferred_followup_is_active(10, 111, 1002.0))
        self.assertTrue(bot._inferred_followup_is_active(10, 222, 1002.0))

    def test_clear_inferred_followup_window_removes_empty_channel_bucket(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        bot._refresh_inferred_followup_window(channel_id=10, user_id=111, now_wall=1000.0)
        bot._clear_inferred_followup_window(10, 111)

        self.assertNotIn(10, bot._inferred_followup_expires_at)

    def test_sleeping_channel_state_clears_all_followup_windows_until_wake(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        bot._refresh_inferred_followup_window(channel_id=10, user_id=111, now_wall=1000.0)
        bot._refresh_inferred_followup_window(channel_id=10, user_id=222, now_wall=1000.0)

        bot._put_channel_to_sleep(10)

        self.assertTrue(bot._channel_is_sleeping(10))
        self.assertNotIn(10, bot._inferred_followup_expires_at)

        bot._wake_channel(10)

        self.assertFalse(bot._channel_is_sleeping(10))


if __name__ == "__main__":
    unittest.main()
