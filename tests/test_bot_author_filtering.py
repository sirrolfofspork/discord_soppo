import os
import unittest
from unittest.mock import patch


BASE_ENV = {
    "DISCORD_BOT_TOKEN": "dummy-token",
    "LLM_BACKEND": "ollama",
}


class BotAuthorConfigTests(unittest.TestCase):
    def test_other_bot_responses_are_disabled_by_default(self):
        from config import load_config

        with patch.dict(os.environ, BASE_ENV, clear=True):
            config = load_config()

        self.assertFalse(config.respond_to_other_bots)

    def test_other_bot_response_config_parses_enabled_and_cooldown(self):
        from config import load_config

        env = {
            **BASE_ENV,
            "RESPOND_TO_OTHER_BOTS": "true",
            "BOT_AUTHOR_COOLDOWN_SECONDS": "45",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertTrue(config.respond_to_other_bots)
        self.assertEqual(config.bot_author_cooldown_seconds, 45.0)


class BotAuthorGateTests(unittest.TestCase):
    def test_self_author_is_always_ignored_even_when_other_bots_enabled(self):
        from bot import should_ignore_message_author

        self.assertTrue(
            should_ignore_message_author(
                author_id=123,
                author_is_bot=True,
                self_user_id=123,
                respond_to_other_bots=True,
                bot_author_cooldown_seconds=0.0,
                last_bot_author_reply_monotonic={},
                now_monotonic=100.0,
            )
        )

    def test_other_bot_author_is_ignored_when_disabled(self):
        from bot import should_ignore_message_author

        self.assertTrue(
            should_ignore_message_author(
                author_id=456,
                author_is_bot=True,
                self_user_id=123,
                respond_to_other_bots=False,
                bot_author_cooldown_seconds=0.0,
                last_bot_author_reply_monotonic={},
                now_monotonic=100.0,
            )
        )

    def test_other_bot_author_is_allowed_when_enabled(self):
        from bot import should_ignore_message_author

        self.assertFalse(
            should_ignore_message_author(
                author_id=456,
                author_is_bot=True,
                self_user_id=123,
                respond_to_other_bots=True,
                bot_author_cooldown_seconds=30.0,
                last_bot_author_reply_monotonic={},
                now_monotonic=100.0,
            )
        )

    def test_other_bot_author_is_ignored_during_bot_author_cooldown(self):
        from bot import should_ignore_message_author

        self.assertTrue(
            should_ignore_message_author(
                author_id=456,
                author_is_bot=True,
                self_user_id=123,
                respond_to_other_bots=True,
                bot_author_cooldown_seconds=30.0,
                last_bot_author_reply_monotonic={456: 80.0},
                now_monotonic=100.0,
            )
        )

    def test_human_author_is_not_subject_to_bot_author_cooldown(self):
        from bot import should_ignore_message_author

        self.assertFalse(
            should_ignore_message_author(
                author_id=789,
                author_is_bot=False,
                self_user_id=123,
                respond_to_other_bots=False,
                bot_author_cooldown_seconds=30.0,
                last_bot_author_reply_monotonic={789: 99.0},
                now_monotonic=100.0,
            )
        )


if __name__ == "__main__":
    unittest.main()
