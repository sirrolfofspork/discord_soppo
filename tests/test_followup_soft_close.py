import asyncio
import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, patch


class FakeAuthor:
    def __init__(self, user_id, display_name, *, bot=False):
        self.id = user_id
        self.display_name = display_name
        self.name = display_name
        self.bot = bot


class FakeGuild:
    def __init__(self, guild_id):
        self.id = guild_id


class FakeReference:
    def __init__(self, *, message_id=None, channel_id=None, guild_id=None, cached_message=None):
        self.message_id = message_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.cached_message = cached_message


class FakeChannel:
    def __init__(self, channel_id=10, name="general", guild=None):
        self.id = channel_id
        self.name = name
        self.guild = guild
        self.sent = []

    async def send(self, content, *, allowed_mentions=None):
        self.sent.append({"content": content, "allowed_mentions": allowed_mentions})


class FakeMessage:
    def __init__(
        self,
        *,
        content="Sash, answer this",
        author=None,
        channel=None,
        guild=None,
        message_id=1000,
        reference=None,
        mentions=None,
    ):
        self.content = content
        self.author = author if author is not None else FakeAuthor(111, "Alice")
        self.channel = channel if channel is not None else FakeChannel(guild=guild)
        self.guild = guild
        self.id = message_id
        self.reference = reference
        self.mentions = mentions if mentions is not None else []


def make_pending_snapshot(**overrides):
    from bot import PendingReplyMessageSnapshot

    values = dict(
        content="Sash, answer this",
        author_id=111,
        author_display="Alice",
        author_is_bot=False,
        channel_id=10,
        guild_id=20,
        message_id=1000,
        reason="name_alias",
        priority=2,
        identity_reset=False,
        reference=None,
    )
    values.update(overrides)
    return PendingReplyMessageSnapshot(**values)  # type: ignore[arg-type]


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


class ReplyCoalescingTests(unittest.IsolatedAsyncioTestCase):
    def test_reply_queue_priority_prefers_identity_then_direct_then_followup(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())

        self.assertEqual(bot._reply_queue_priority("name_alias"), 2)
        self.assertEqual(bot._reply_queue_priority("inferred_followup"), 1)
        self.assertEqual(bot._reply_queue_priority("spontaneous"), 0)
        self.assertEqual(bot._reply_queue_priority("name_alias", identity_reset=True), 3)

    def test_pending_reply_coalescing_keeps_latest_equal_or_higher_priority(self):
        from bot import PendingReplyMessageSnapshot, SoppoBot

        bot = SoppoBot(make_config())
        guild = FakeGuild(20)
        channel = FakeChannel(guild=guild)
        followup_1 = FakeMessage(content="followup one", channel=channel, guild=guild, message_id=1)
        followup_2 = FakeMessage(content="followup two", channel=channel, guild=guild, message_id=2)
        direct = FakeMessage(content="Sash direct", channel=channel, guild=guild, message_id=3)
        later_followup = FakeMessage(content="followup three", channel=channel, guild=guild, message_id=4)

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
        self.assertIsInstance(bot._pending_reply_messages[10], PendingReplyMessageSnapshot)
        self.assertEqual(bot._pending_reply_messages[10].message_id, 2)
        self.assertEqual(bot._pending_reply_messages[10].content, "followup two")

        self.assertTrue(
            bot._store_pending_reply_message(
                channel_id=10,
                message=direct,  # type: ignore[arg-type]
                reason="name_alias",
            )
        )
        self.assertEqual(bot._pending_reply_messages[10].message_id, 3)
        self.assertEqual(bot._pending_reply_messages[10].reason, "name_alias")

        self.assertFalse(
            bot._store_pending_reply_message(
                channel_id=10,
                message=later_followup,  # type: ignore[arg-type]
                reason="inferred_followup",
            )
        )
        self.assertEqual(bot._pending_reply_messages[10].message_id, 3)
        self.assertEqual(bot._pending_reply_messages[10].content, "Sash direct")

    def test_pending_reply_queue_stores_frozen_scalar_snapshot(self):
        from bot import PendingReplyMessageSnapshot, SoppoBot

        bot = SoppoBot(make_config())
        guild = FakeGuild(20)
        channel = FakeChannel(guild=guild)
        author = FakeAuthor(111, "Alice")
        referenced_author = FakeAuthor(42, "SOPPO", bot=True)
        referenced = FakeMessage(
            content="old bot reply",
            author=referenced_author,
            channel=channel,
            guild=guild,
            message_id=555,
        )
        reference = FakeReference(message_id=555, channel_id=10, guild_id=20, cached_message=referenced)
        live = FakeMessage(
            content="Sash, original content",
            author=author,
            channel=channel,
            guild=guild,
            message_id=777,
            reference=reference,
        )

        stored = bot._store_pending_reply_message(
            channel_id=10,
            message=live,  # type: ignore[arg-type]
            reason="reply_chain",
            identity_reset=True,
            referenced_message=referenced,  # type: ignore[arg-type]
        )

        self.assertTrue(stored)
        snapshot = bot._pending_reply_messages[10]
        self.assertIsInstance(snapshot, PendingReplyMessageSnapshot)
        self.assertIsNot(snapshot, live)
        self.assertEqual(snapshot.content, "Sash, original content")
        self.assertEqual(snapshot.author_id, 111)
        self.assertEqual(snapshot.author_display, "Alice")
        self.assertEqual(snapshot.channel_id, 10)
        self.assertEqual(snapshot.guild_id, 20)
        self.assertEqual(snapshot.message_id, 777)
        self.assertEqual(snapshot.reason, "reply_chain")
        self.assertEqual(snapshot.priority, 3)
        self.assertTrue(snapshot.identity_reset)
        self.assertIsNotNone(snapshot.reference)
        self.assertEqual(snapshot.reference.message_id, 555)
        self.assertEqual(snapshot.reference.resolved_author_id, 42)
        with self.assertRaises(FrozenInstanceError):
            snapshot.content = "changed"  # type: ignore[misc]

    def test_live_message_mutation_after_queue_does_not_change_snapshot(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        guild = FakeGuild(20)
        channel = FakeChannel(guild=guild)
        author = FakeAuthor(111, "Alice")
        referenced_author = FakeAuthor(42, "SOPPO", bot=True)
        referenced = FakeMessage(
            content="original referenced",
            author=referenced_author,
            channel=channel,
            guild=guild,
            message_id=555,
        )
        reference = FakeReference(message_id=555, channel_id=10, guild_id=20, cached_message=referenced)
        live = FakeMessage(
            content="Sash, original content",
            author=author,
            channel=channel,
            guild=guild,
            message_id=777,
            reference=reference,
        )
        bot._store_pending_reply_message(
            channel_id=10,
            message=live,  # type: ignore[arg-type]
            reason="reply_chain",
            referenced_message=referenced,  # type: ignore[arg-type]
        )

        live.content = "MUTATED content"
        live.author.id = 222
        live.author.display_name = "Mallory"
        live.channel.id = 99
        live.guild.id = 88
        live.id = 999
        live.reference.message_id = 444
        referenced.author.id = 333
        referenced.author.display_name = "ChangedBot"

        snapshot = bot._pending_reply_messages[10]
        self.assertEqual(snapshot.content, "Sash, original content")
        self.assertEqual(snapshot.author_id, 111)
        self.assertEqual(snapshot.author_display, "Alice")
        self.assertEqual(snapshot.channel_id, 10)
        self.assertEqual(snapshot.guild_id, 20)
        self.assertEqual(snapshot.message_id, 777)
        self.assertIsNotNone(snapshot.reference)
        self.assertEqual(snapshot.reference.message_id, 555)
        self.assertEqual(snapshot.reference.resolved_author_id, 42)
        self.assertEqual(snapshot.reference.resolved_author_display, "SOPPO")

    def test_sleep_clears_pending_reply_for_channel(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        guild = FakeGuild(20)
        channel = FakeChannel(guild=guild)
        bot._store_pending_reply_message(
            channel_id=10,
            message=FakeMessage(channel=channel, guild=guild),  # type: ignore[arg-type]
            reason="name_alias",
        )

        bot._put_channel_to_sleep(10)

        self.assertNotIn(10, bot._pending_reply_messages)

    async def test_snapshot_backed_processing_uses_captured_values(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config(summary_regen_message_count=999))
        bot._connection.user = FakeAuthor(42, "SOPPO", bot=True)
        guild = FakeGuild(20)
        channel = FakeChannel(guild=guild)
        author = FakeAuthor(111, "Alice")
        live = FakeMessage(
            content="Sash, captured request",
            author=author,
            channel=channel,
            guild=guild,
            message_id=777,
        )
        bot._store_pending_reply_message(
            channel_id=10,
            message=live,  # type: ignore[arg-type]
            reason="name_alias",
        )
        snapshot = bot._pop_pending_reply_message(10)
        self.assertIsNotNone(snapshot)

        live.content = "MUTATED request"
        live.author.id = 222
        live.author.display_name = "Mallory"
        live.id = 999

        bot.get_channel = lambda channel_id: channel if channel_id == 10 else None  # type: ignore[method-assign]
        with (
            patch("bot.is_supported_message_channel", return_value=True),
            patch("bot.generate_reply", new=AsyncMock(return_value="captured reply")) as mock_generate,
            patch.object(bot, "_maybe_regenerate_neutral_summary", new=AsyncMock(return_value=False)),
        ):
            await bot._handle_message(snapshot, coalesced=True)

        self.assertEqual(len(channel.sent), 1)
        self.assertEqual(channel.sent[0]["content"], "captured reply")
        mock_generate.assert_awaited_once()
        messages = mock_generate.await_args.kwargs["messages"]
        latest = messages[-1]["content"].split("\n", 1)[1]
        latest_payload = json.loads(latest)
        self.assertEqual(latest_payload["author"], "Alice")
        self.assertEqual(latest_payload["content"], "Sash, captured request")
        joined = "\n".join(str(item.get("content", "")) for item in messages)
        self.assertNotIn("MUTATED request", joined)
        self.assertNotIn("Mallory", joined)
        hist = list(bot._history_for(10))
        self.assertEqual(hist[0]["author_id"], 111)
        self.assertEqual(hist[0]["author_display"], "Alice")
        self.assertEqual(set(bot._last_reply_monotonic.keys()), {10})

    async def test_coalesced_drain_task_is_retained_named_and_removed_on_success(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        handled = asyncio.Event()

        async def handle_snapshot(snapshot, *, coalesced=False):
            self.assertTrue(coalesced)
            self.assertEqual(snapshot.message_id, 1234)
            handled.set()

        with patch.object(bot, "_handle_message", new=handle_snapshot):
            scheduled = bot._schedule_coalesced_drain(make_pending_snapshot(message_id=1234))
            self.assertTrue(scheduled)
            self.assertEqual(len(bot._coalesced_drain_tasks), 1)
            task = next(iter(bot._coalesced_drain_tasks))
            self.assertEqual(task.get_name(), "soppo-coalesced-drain:10:1234")
            await handled.wait()
            await asyncio.sleep(0)

        self.assertEqual(bot._coalesced_drain_tasks, set())

    async def test_coalesced_drain_task_exception_is_observed_and_removed(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())

        async def fail_snapshot(snapshot, *, coalesced=False):
            raise RuntimeError("synthetic drain failure")

        with (
            patch.object(bot, "_handle_message", new=fail_snapshot),
            self.assertLogs("bot", level="ERROR") as logs,
        ):
            self.assertTrue(bot._schedule_coalesced_drain(make_pending_snapshot(message_id=2222)))
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        self.assertEqual(bot._coalesced_drain_tasks, set())
        self.assertTrue(any("Coalesced SOPPO drain task failed" in line for line in logs.output))

    async def test_close_cancels_and_awaits_drains_and_clears_pending_active_state(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def blocked_snapshot(snapshot, *, coalesced=False):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        bot._active_reply_channels.add(10)
        bot._pending_reply_messages[10] = make_pending_snapshot(message_id=3333)
        with (
            patch.object(bot, "_handle_message", new=blocked_snapshot),
            patch("discord.Client.close", new=AsyncMock()) as mock_super_close,
        ):
            self.assertTrue(bot._schedule_coalesced_drain(make_pending_snapshot(message_id=4444)))
            await started.wait()
            await bot.close()

        self.assertTrue(cancelled.is_set())
        self.assertTrue(bot._shutdown_started)
        self.assertEqual(bot._pending_reply_messages, {})
        self.assertEqual(bot._active_reply_channels, set())
        self.assertEqual(bot._coalesced_drain_tasks, set())
        mock_super_close.assert_awaited_once()

    async def test_no_coalesced_drain_is_scheduled_after_shutdown_begins(self):
        from bot import SoppoBot

        bot = SoppoBot(make_config())
        bot._shutdown_started = True

        with patch("asyncio.create_task") as mock_create_task:
            scheduled = bot._schedule_coalesced_drain(make_pending_snapshot(message_id=5555))

        self.assertFalse(scheduled)
        self.assertEqual(bot._coalesced_drain_tasks, set())
        mock_create_task.assert_not_called()

    async def test_run_bot_closes_client_on_cancellation_and_error(self):
        from bot import run_bot

        for error in (asyncio.CancelledError(), RuntimeError("start failed")):
            client = AsyncMock()
            client.start.side_effect = error
            client.close = AsyncMock()

            with self.subTest(error=type(error).__name__):
                with patch("bot.SoppoBot", return_value=client):
                    with self.assertRaises(type(error)):
                        await run_bot(make_config())

            client.start.assert_awaited_once_with("dummy")
            client.close.assert_awaited_once()


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
