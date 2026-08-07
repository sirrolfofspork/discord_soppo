from collections import deque
import hashlib
import unittest


class ReplyPromptPhase1Tests(unittest.TestCase):
    def test_spontaneous_prompt_uses_only_current_trigger_as_raw_history(self):
        from bot import build_prompt_messages
        from prompts import build_user_message_wrapper

        stale_user = "PHASE1_STALE_USER_SENTINEL_1201"
        stale_assistant = "PHASE1_STALE_ASSISTANT_SENTINEL_1202"
        current_trigger = build_user_message_wrapper("Alice", "PHASE1_CURRENT_TRIGGER_SENTINEL_1203")
        messages = build_prompt_messages(
            system_prompt="CORE",
            speaker_context="SPEAKER CONTEXT",
            channel_summary_block="SUMMARY BLOCK WITH BACKGROUND",
            channel_memory_block="STRUCTURED MEMORY BLOCK",
            lore_block="LORE BLOCK",
            returning_hint="RETURNING HINT",
            history=deque(
                [
                    {"role": "user", "content": stale_user},
                    {"role": "assistant", "content": stale_assistant},
                ]
            ),
            recent_raw_turns=3,
            response_reason="spontaneous",
            current_user_turn={"role": "user", "content": current_trigger},
        )

        joined = "\n".join(m["content"] for m in messages)
        self.assertIn("SPEAKER CONTEXT", joined)
        self.assertIn("SUMMARY BLOCK WITH BACKGROUND", joined)
        self.assertIn("STRUCTURED MEMORY BLOCK", joined)
        self.assertIn("LORE BLOCK", joined)
        self.assertIn("RETURNING HINT", joined)
        self.assertNotIn(stale_user, joined)
        self.assertNotIn(stale_assistant, joined)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(
            messages[-1]["content"],
            "[Newest live Discord message — answer this message directly now]\n"
            f"{current_trigger}",
        )

    def test_spontaneous_prompt_requires_current_user_turn(self):
        from bot import build_prompt_messages

        with self.assertRaisesRegex(
            ValueError,
            "spontaneous prompt requires current_user_turn with role=user",
        ):
            build_prompt_messages(
                system_prompt="CORE",
                history=deque([{"role": "user", "content": "stale raw history"}]),
                response_reason="spontaneous",
                current_user_turn=None,
            )

    def test_spontaneous_prompt_requires_user_role_current_turn(self):
        from bot import build_prompt_messages

        with self.assertRaisesRegex(
            ValueError,
            "spontaneous prompt requires current_user_turn with role=user",
        ):
            build_prompt_messages(
                system_prompt="CORE",
                history=deque([{"role": "user", "content": "stale raw history"}]),
                response_reason="spontaneous",
                current_user_turn={"role": "assistant", "content": "wrong role"},
            )

    def test_non_spontaneous_prompt_keeps_recent_raw_turn_behavior(self):
        from bot import build_prompt_messages

        messages = build_prompt_messages(
            system_prompt="CORE",
            history=deque(
                [
                    {"role": "user", "content": "raw-1"},
                    {"role": "assistant", "content": "raw-2"},
                    {"role": "user", "content": "raw-3"},
                    {"role": "assistant", "content": "raw-4"},
                ]
            ),
            recent_raw_turns=3,
            response_reason="trigger",
            current_user_turn={"role": "user", "content": "ignored for direct prompt"},
        )

        self.assertEqual(
            [m["content"] for m in messages],
            ["CORE", "raw-2", "raw-3", "raw-4"],
        )

    def test_request_diagnostics_are_privacy_safe_and_deterministic(self):
        from bot import build_reply_request_diagnostics

        raw_trigger = "private raw Discord trigger PHASE1_SECRET_CONTENT"
        diagnostics = build_reply_request_diagnostics(
            reason="spontaneous",
            channel_id=123,
            message_id=456,
            prompt_messages=[
                {"role": "system", "content": "system text"},
                {"role": "system", "content": "summary text"},
                {"role": "user", "content": "wrapped trigger text"},
            ],
            triggering_content=raw_trigger,
        )

        self.assertEqual(diagnostics["reason"], "spontaneous")
        self.assertEqual(diagnostics["channel_id"], 123)
        self.assertEqual(diagnostics["message_id"], 456)
        self.assertEqual(diagnostics["prompt_message_count"], 3)
        self.assertEqual(diagnostics["prompt_role_counts"], {"system": 2, "user": 1})
        self.assertEqual(diagnostics["prompt_char_count"], len("system textsummary textwrapped trigger text"))
        self.assertEqual(
            diagnostics["trigger_content_sha256"],
            hashlib.sha256(raw_trigger.encode("utf-8")).hexdigest()[:12],
        )
        self.assertNotIn(raw_trigger, str(diagnostics))
        self.assertNotIn("PHASE1_SECRET_CONTENT", str(diagnostics))


if __name__ == "__main__":
    unittest.main()
