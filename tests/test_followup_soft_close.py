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
