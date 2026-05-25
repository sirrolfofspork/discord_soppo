import os
import unittest
from unittest.mock import patch


BASE_ENV = {
    "DISCORD_BOT_TOKEN": "dummy-token",
    "LLM_BACKEND": "ollama",
}


class ConfigChannelIdTests(unittest.TestCase):
    def test_allowed_channel_ids_parse_comma_separated_ids(self):
        from config import load_config

        env = {
            **BASE_ENV,
            "DISCORD_ALLOWED_CHANNEL_IDS": "111, 222,,333 ",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.discord_allowed_channel_ids, (111, 222, 333))

    def test_allowed_channel_ids_empty_falls_back_to_name_configuration(self):
        from config import load_config

        env = {
            **BASE_ENV,
            "DISCORD_ALLOWED_CHANNEL_IDS": "  ",
            "DISCORD_CHANNEL_NAME": "bot-talk",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_config()

        self.assertEqual(config.discord_allowed_channel_ids, ())
        self.assertEqual(config.discord_channel_name, "bot-talk")


class ChannelGateTests(unittest.TestCase):
    def test_channel_ids_take_priority_over_matching_channel_name(self):
        from bot import channel_is_allowed

        self.assertFalse(
            channel_is_allowed(
                channel_id=999,
                channel_name="general",
                allowed_channel_ids=(123,),
                fallback_channel_name="general",
            )
        )
        self.assertTrue(
            channel_is_allowed(
                channel_id=123,
                channel_name="not-general",
                allowed_channel_ids=(123,),
                fallback_channel_name="general",
            )
        )

    def test_empty_channel_ids_fall_back_to_case_insensitive_name(self):
        from bot import channel_is_allowed

        self.assertTrue(
            channel_is_allowed(
                channel_id=999,
                channel_name="General",
                allowed_channel_ids=(),
                fallback_channel_name="general",
            )
        )
        self.assertFalse(
            channel_is_allowed(
                channel_id=999,
                channel_name="bot-talk",
                allowed_channel_ids=(),
                fallback_channel_name="general",
            )
        )


if __name__ == "__main__":
    unittest.main()
