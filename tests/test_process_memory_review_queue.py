import unittest


class ProcessMemoryReviewQueueGuardTests(unittest.TestCase):
    def test_apply_blocked_when_service_active_without_force(self):
        from tools.process_memory_review_queue import assert_safe_to_apply_memories

        warning = assert_safe_to_apply_memories(force=False, is_active_runner=lambda: "active")

        self.assertIsNotNone(warning)
        assert warning is not None
        self.assertIn("soppo-discord.service", warning)
        self.assertIn("--force", warning)

    def test_apply_allowed_when_service_inactive(self):
        from tools.process_memory_review_queue import assert_safe_to_apply_memories

        self.assertIsNone(assert_safe_to_apply_memories(force=False, is_active_runner=lambda: "inactive"))

    def test_apply_allowed_with_force_even_when_service_active(self):
        from tools.process_memory_review_queue import assert_safe_to_apply_memories

        self.assertIsNone(assert_safe_to_apply_memories(force=True, is_active_runner=lambda: "active"))


if __name__ == "__main__":
    unittest.main()
