"""
Discord bot: listens in the configured text channel, decides when to reply,
maintains rolling chat context, and calls the configured LLM backend for completions.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from collections import deque
from functools import lru_cache
from typing import Any, Literal, cast

import discord

from config import Config
from llm_client import (
    LLMBackend,
    OllamaError,
    OpenAIClientError,
    generate_reply,
    trim_messages_to_max_chars,
)
from lore import build_lore_context_block, find_relevant_lore, load_lore_store
from prompts import (
    build_assistant_message_wrapper,
    build_current_speaker_context,
    build_system_prompt,
    build_user_message_wrapper,
)
from user_profiles import UserProfilesMap, load_user_profiles

logger = logging.getLogger(__name__)

ELLIPSIS = "..."

# Injected as an extra system message when rare "returning user" checks pass (no extra Discord post).
RETURNING_USER_LLM_HINT = (
    "The current speaker seems to be returning after a noticeable absence in this channel. "
    "If it feels natural, briefly acknowledge that they are back before answering. "
    "Keep it short and do not make a big deal of it."
)

# Trigger prefix: messages containing this token (word boundary) force a reply
TRIGGER_COMMAND = "!soppo"

ResponseReason = Literal[
    "mention",
    "reply_chain",
    "trigger",
    "spontaneous",
    "name_alias",
    "inferred_followup",
]

# Refresh sliding follow-up window after these reply kinds (not spontaneous).
_FOLLOWUP_WINDOW_REFRESH_REASONS: frozenset[str] = frozenset(
    {"mention", "reply_chain", "trigger", "name_alias", "inferred_followup"}
)

# One-line reactions / noise — not treated as continuing a SOPPO-directed thread.
_AMBIENT_CHATTER = re.compile(
    r"^("
    r"lol|lmao|rofl|kek|ok+|k\.|kk|mhm|uh+ huh|"
    r"yeah|yep|yup|no+|nah|nope|"
    r"haha+|heh|hehe+|lul|"
    r"gg|rip|oof|bruh|same|this|facts|mood|"
    r"thanks|thx|ty|np|yw"
    r")\s*[!?.]*\s*$",
    re.IGNORECASE,
)


def channel_name_matches(channel: discord.abc.GuildChannel, expected: str) -> bool:
    """True if this text channel's name matches the configured name (case-insensitive)."""
    if not isinstance(channel, discord.TextChannel):
        return False
    return channel.name.lower() == expected.lower()


def message_has_trigger(content: str) -> bool:
    """True if the user used the `!soppo` trigger as its own word/token."""
    if not content:
        return False
    # Word boundary: !soppo not preceded by word char; optional punctuation after
    return bool(re.search(r"(?<!\w)!soppo\b", content, flags=re.IGNORECASE))


def _alias_regex_pattern(alias: str) -> str:
    """
    Whole-word / whole-phrase match, case-insensitive.
    Multi-word aliases allow flexible whitespace between tokens.
    Uses (?<!\\w) / (?!\\w) so names do not match inside longer tokens (e.g. xsoppo).
    """
    tokens = alias.split()
    if not tokens:
        return ""
    inner = r"\s+".join(re.escape(t) for t in tokens)
    return rf"(?<!\w){inner}(?!\w)"


@lru_cache(maxsize=128)
def _cached_alias_pattern(alias: str) -> re.Pattern[str]:
    pat = _alias_regex_pattern(alias)
    return re.compile(pat, flags=re.IGNORECASE)


def message_has_name_alias(content: str, aliases: tuple[str, ...]) -> bool:
    """
    True if `content` contains one of the configured aliases as a distinct word or phrase.

    Case-insensitive; punctuation next to the alias is fine; does not match substrings
    glued inside unrelated words. Longer aliases are checked first.
    """
    if not content or not aliases:
        return False
    text = content.strip()
    if not text:
        return False
    for alias in sorted(aliases, key=len, reverse=True):
        if not alias.strip():
            continue
        if _cached_alias_pattern(alias).search(text):
            return True
    return False


def is_reply_to_bot(
    referenced: discord.Message | None,
    bot_user: discord.ClientUser,
) -> bool:
    """True if the user is replying to a message authored by the bot."""
    if referenced is None:
        return False
    return referenced.author.id == bot_user.id


def is_directly_addressed(
    message: discord.Message,
    bot_user: discord.ClientUser,
    referenced_message: discord.Message | None,
    name_aliases: tuple[str, ...],
) -> bool:
    """Trigger, mention, reply to bot, or natural-language name alias."""
    if message_has_trigger(message.content):
        return True
    if bot_user in message.mentions:
        return True
    if is_reply_to_bot(referenced_message, bot_user):
        return True
    if message_has_name_alias(message.content, name_aliases):
        return True
    return False


def direct_response_reason(
    message: discord.Message,
    bot_user: discord.ClientUser,
    referenced_message: discord.Message | None,
    name_aliases: tuple[str, ...],
) -> ResponseReason:
    """Classify why a direct-address reply is happening (for logging)."""
    if message_has_trigger(message.content):
        return "trigger"
    if is_reply_to_bot(referenced_message, bot_user):
        return "reply_chain"
    if bot_user in message.mentions:
        return "mention"
    if message_has_name_alias(message.content, name_aliases):
        return "name_alias"
    return "mention"


def message_mentions_only_other_users(message: discord.Message, bot_user: discord.ClientUser) -> bool:
    """True if the message @-mentions someone other than the bot (clearly talking to others)."""
    if not message.mentions:
        return False
    return bot_user not in message.mentions


def is_reply_to_someone_other_than_soppo(
    referenced: discord.Message | None,
    bot_user: discord.ClientUser,
) -> bool:
    """True if this message is a reply to anyone except SOPPO (side thread → not inferred follow-up)."""
    if referenced is None:
        return False
    return referenced.author.id != bot_user.id


def is_likely_ambient_chatter(content: str) -> bool:
    """Heuristic: very short or generic reaction-only lines are not inferred follow-ups."""
    s = content.strip()
    if len(s) <= 1:
        return True
    if _AMBIENT_CHATTER.match(s):
        return True
    return False


def try_spontaneous_reply(
    *,
    last_reply_monotonic: float | None,
    cooldown_seconds: float,
    spontaneous_chance: float,
    now_monotonic: float,
) -> tuple[bool, Literal["spontaneous"] | None]:
    """
    Random channel reply when not directly addressed and not in an inferred follow-up turn.

    Respects the same post-reply cooldown as before.
    """
    if last_reply_monotonic is not None:
        elapsed = now_monotonic - last_reply_monotonic
        if elapsed < cooldown_seconds:
            return False, None

    if random.random() < spontaneous_chance:
        return True, "spontaneous"

    return False, None


def scrub_discord_mass_pings(text: str) -> str:
    """Reduce risk of @everyone / @here in model output."""
    if not text:
        return text
    # Zero-width space after @ so Discord does not treat it as a mention
    t = re.sub(r"@everyone\b", "@\u200beveryone", text, flags=re.IGNORECASE)
    t = re.sub(r"@here\b", "@\u200bhere", t, flags=re.IGNORECASE)
    return t


def apply_soft_reply_limit(text: str, soft_limit: int) -> str:
    """
    If text is longer than `soft_limit`, trim preferring the last sentence end,
    else last space, else a hard cut. Appends ... when trimmed.
    """
    text = text.strip()
    if not text:
        return text
    el = len(ELLIPSIS)
    if soft_limit <= el + 4:
        return text[:soft_limit]
    if len(text) <= soft_limit:
        return text

    budget = soft_limit - el
    head = text[:budget]
    min_keep = max(16, budget // 6)

    last_sent = None
    for m in re.finditer(r"[.!?](?:\s+|$)", head):
        last_sent = m
    if last_sent is not None and last_sent.end() >= min_keep:
        return text[: last_sent.end()].rstrip() + ELLIPSIS

    sp = head.rfind(" ")
    if sp >= min_keep:
        return text[:sp].rstrip() + ELLIPSIS

    return head.rstrip() + ELLIPSIS


def _best_chunk_cut(window: str, max_body: int) -> int:
    """How many chars to take from the start of window (<= max_body), preferring natural breaks."""
    w = window[:max_body]
    if len(w) < max_body:
        return len(w)
    min_ok = max(8, max_body // 12)
    for sep in ("\n\n", "\n"):
        i = w.rfind(sep)
        if i >= min_ok:
            return i + len(sep)
    last = None
    for m in re.finditer(r"[.!?](?:\s|$)", w):
        last = m
    if last is not None and last.end() >= min_ok:
        return last.end()
    sp = w.rfind(" ")
    if sp >= min_ok:
        return sp + 1
    return max_body


def split_text_for_discord(text: str, hard_limit: int) -> list[str]:
    """
    Normalize whitespace, then split into chunks that never exceed `hard_limit`.
    Prefers paragraph breaks, then sentences, then spaces, then hard cut.
    Appends ... when a chunk is cut mid-thought and more text follows.
    """
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if not text:
        return []

    el = len(ELLIPSIS)
    if hard_limit < el + 8:
        hard_limit = el + 8

    if len(text) <= hard_limit:
        return [text]

    chunks: list[str] = []
    pos = 0
    n = len(text)
    while pos < n:
        remaining = n - pos
        if remaining <= hard_limit:
            chunks.append(text[pos:n].strip())
            break

        max_body = hard_limit - el
        window = text[pos : pos + max_body]
        cut_local = _best_chunk_cut(window, max_body)
        chunk_raw = text[pos : pos + cut_local].rstrip()
        pos += cut_local
        while pos < n and text[pos] in " \n\t":
            pos += 1

        if pos < n:
            stripped = chunk_raw.rstrip()
            ends_clean = bool(stripped) and stripped[-1] in ".!?"
            if ends_clean:
                chunk = chunk_raw
            else:
                body_max = hard_limit - el
                body = chunk_raw[:body_max].rstrip() + ELLIPSIS
                chunk = body
        else:
            chunk = chunk_raw
        if chunk:
            chunks.append(chunk)

    return [c for c in chunks if c]


class SoppoBot(discord.Client):
    """
    Minimal subclass: on_ready logs, on_message handles the pipeline.

    Extension points: slash commands can be registered similarly later;
    per-channel controls can branch on `message.channel.id` or guild settings.
    """

    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.message_content = True  # required to read message text
        intents.guilds = True
        intents.messages = True

        super().__init__(intents=intents)
        self.config = config
        self._lore_store: dict[str, Any] = load_lore_store()
        self._user_profiles: UserProfilesMap = load_user_profiles()
        # channel_id -> deque of {"role": "user"|"assistant", "content": str}
        self._history: dict[int, deque[dict[str, str]]] = {}
        self._last_reply_monotonic: dict[int, float] = {}
        self._last_bot_text: dict[int, str] = {}
        # Returning-user tracking: wall clock for "absence" gap; monotonic for greeting cooldowns
        self._last_user_post_wall: dict[int, dict[int, float]] = {}
        self._last_user_greeted_mono: dict[int, dict[int, float]] = {}
        self._last_channel_greet_mono: dict[int, float] = {}
        # channel_id -> user_id -> expires_at (time.time); sliding window after SOPPO-directed messages
        self._inferred_followup_expires_at: dict[int, dict[int, float]] = {}

    def _history_for(self, channel_id: int) -> deque[dict[str, str]]:
        if channel_id not in self._history:
            self._history[channel_id] = deque(maxlen=self.config.max_context_messages)
        return self._history[channel_id]

    def _get_user_profile(self, user_id: int) -> dict[str, Any] | None:
        """Return the profile dict for this Discord user ID, or None if unknown."""
        return self._user_profiles.get(str(user_id))

    def _should_add_returning_user_greeting(
        self,
        *,
        channel_id: int,
        user_id: int,
        now_monotonic: float,
    ) -> bool:
        """
        True only if the user was quiet long enough (wall clock), greeting cooldowns
        (monotonic) allow it, and random chance passes. Does not send Discord traffic.
        """
        now_wall = time.time()
        prev_wall = self._last_user_post_wall.get(channel_id, {}).get(user_id)
        if prev_wall is None:
            return False
        if now_wall - prev_wall < self.config.returning_user_threshold_seconds:
            return False

        last_user_greet = self._last_user_greeted_mono.get(channel_id, {}).get(user_id)
        if last_user_greet is not None:
            if now_monotonic - last_user_greet < self.config.user_greeting_cooldown_seconds:
                return False

        last_ch_greet = self._last_channel_greet_mono.get(channel_id)
        if last_ch_greet is not None:
            if now_monotonic - last_ch_greet < self.config.channel_greeting_cooldown_seconds:
                return False

        if random.random() >= self.config.returning_user_greeting_chance:
            return False

        return True

    def _record_returning_user_greeting(
        self,
        channel_id: int,
        user_id: int,
        now_monotonic: float,
    ) -> None:
        """Call after a successful reply that used the returning-user LLM hint."""
        self._last_user_greeted_mono.setdefault(channel_id, {})[user_id] = now_monotonic
        self._last_channel_greet_mono[channel_id] = now_monotonic

    def _touch_user_channel_activity(self, channel_id: int, user_id: int, now_wall: float) -> None:
        """Record that this user posted in this channel (wall clock), after handling the message."""
        self._last_user_post_wall.setdefault(channel_id, {})[user_id] = now_wall

    def _inferred_followup_is_active(self, channel_id: int, user_id: int, now_wall: float) -> bool:
        """True if this user still has a non-expired follow-up window in this channel."""
        by_ch = self._inferred_followup_expires_at.get(channel_id)
        if not by_ch:
            return False
        exp = by_ch.get(user_id)
        if exp is None:
            return False
        if now_wall >= exp:
            del by_ch[user_id]
            if not by_ch:
                del self._inferred_followup_expires_at[channel_id]
            return False
        return True

    def _refresh_inferred_followup_window(self, channel_id: int, user_id: int, now_wall: float) -> None:
        """Extend sliding window so the user can keep talking without re-addressing SOPPO."""
        w = self.config.inferred_followup_window_seconds
        self._inferred_followup_expires_at.setdefault(channel_id, {})[user_id] = now_wall + w

    def _should_accept_inferred_followup(
        self,
        message: discord.Message,
        referenced: discord.Message | None,
        bot_user: discord.ClientUser,
        channel_id: int,
        user_id: int,
        now_wall: float,
    ) -> bool:
        """
        Inferred follow-up: same user/channel, window not expired, and message is not clearly
        for someone else, not a reply to another human, and not throwaway ambient chatter.
        """
        if not self._inferred_followup_is_active(channel_id, user_id, now_wall):
            return False
        if message_mentions_only_other_users(message, bot_user):
            return False
        if is_reply_to_someone_other_than_soppo(referenced, bot_user):
            return False
        if is_likely_ambient_chatter(message.content):
            return False
        return True

    async def _resolve_referenced_message(
        self,
        message: discord.Message,
    ) -> discord.Message | None:
        """Best-effort: message being replied to (for reply-chain detection)."""
        ref = message.reference
        if ref is None:
            return None
        if ref.cached_message is not None:
            return ref.cached_message
        if ref.message_id is None:
            return None
        try:
            return await message.channel.fetch_message(ref.message_id)
        except (discord.NotFound, discord.HTTPException) as e:
            logger.debug("Could not fetch referenced message: %s", e)
            return None

    async def setup_hook(self) -> None:
        # Reserved for future: sync app commands, etc.
        return

    async def on_ready(self) -> None:
        user = self.user
        name = user.name if user else "unknown"
        logger.info("Logged in as %s (id=%s)", name, user.id if user else "?")

        guild_names = [g.name for g in self.guilds]
        logger.info("Connected to %d guild(s): %s", len(guild_names), guild_names or "(none)")
        logger.info("Monitored channel name: #%s (case-insensitive)", self.config.discord_channel_name)
        if self.config.llm_backend == "openai":
            logger.info("LLM backend: openai (model=%s)", self.config.openai_model)
        else:
            logger.info(
                "LLM backend: ollama (url=%s, model=%s)",
                self.config.ollama_url,
                self.config.ollama_model,
            )
        logger.info("Spontaneous reply chance: %.2f", self.config.spontaneous_reply_chance)
        logger.info("Reply cooldown: %.1f seconds", self.config.reply_cooldown_seconds)
        na = self.config.bot_name_aliases
        if na:
            logger.info("Name aliases for direct-address (%d): %s", len(na), ", ".join(na))
        else:
            logger.info("Name aliases: (none — set BOT_NAME_ALIASES in .env)")
        logger.info(
            "Reply limits: soft=%d chars, hard=%d chars per message",
            self.config.discord_reply_soft_limit,
            self.config.discord_reply_hard_limit,
        )
        logger.info(
            "Returning-user hint: absence≥%.0fs wall, user_cd≥%.0fs mono, channel_cd≥%.0fs mono, chance=%.2f",
            self.config.returning_user_threshold_seconds,
            self.config.user_greeting_cooldown_seconds,
            self.config.channel_greeting_cooldown_seconds,
            self.config.returning_user_greeting_chance,
        )
        logger.info(
            "Inferred follow-up window: %.0f s wall-clock (per user/channel, expires_at)",
            self.config.inferred_followup_window_seconds,
        )

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if self.user and message.author.id == self.user.id:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if not channel_name_matches(message.channel, self.config.discord_channel_name):
            return

        bot_user = self.user
        if bot_user is None:
            return

        ch_id = message.channel.id
        uid = message.author.id
        now_wall = time.time()
        now_mono = time.monotonic()

        try:
            referenced = await self._resolve_referenced_message(message)

            last = self._last_reply_monotonic.get(ch_id)
            aliases = self.config.bot_name_aliases
            if is_directly_addressed(message, bot_user, referenced, aliases):
                should = True
                reason: ResponseReason | None = direct_response_reason(
                    message, bot_user, referenced, aliases
                )
            elif self._should_accept_inferred_followup(
                message,
                referenced,
                bot_user,
                ch_id,
                uid,
                now_wall,
            ):
                should = True
                reason = "inferred_followup"
            else:
                should, reason = try_spontaneous_reply(
                    last_reply_monotonic=last,
                    cooldown_seconds=self.config.reply_cooldown_seconds,
                    spontaneous_chance=self.config.spontaneous_reply_chance,
                    now_monotonic=now_mono,
                )
            if not should:
                # Still record user lines into context so the model sees the room
                hist = self._history_for(ch_id)
                hist.append(
                    {
                        "role": "user",
                        "content": build_user_message_wrapper(
                            message.author.display_name,
                            message.content,
                        ),
                    }
                )
                return

            hist = self._history_for(ch_id)
            user_line = build_user_message_wrapper(message.author.display_name, message.content)
            hist.append({"role": "user", "content": user_line})

            last_bot = self._last_bot_text.get(ch_id)
            llm_messages: list[dict[str, Any]] = [
                {"role": "system", "content": build_system_prompt(last_bot_reply=last_bot)}
            ]
            profile = self._get_user_profile(message.author.id)
            speaker_context = build_current_speaker_context(
                display_name=message.author.display_name,
                user_id=message.author.id,
                profile=profile,
            )
            if speaker_context:
                llm_messages.append({"role": "system", "content": speaker_context})

            lore_matches = find_relevant_lore(message.content, self._lore_store)
            lore_block = build_lore_context_block(lore_matches)
            if lore_block:
                llm_messages.append({"role": "system", "content": lore_block})

            add_returning_hint = self._should_add_returning_user_greeting(
                channel_id=ch_id,
                user_id=uid,
                now_monotonic=now_mono,
            )
            if add_returning_hint:
                llm_messages.append({"role": "system", "content": RETURNING_USER_LLM_HINT})

            for turn in hist:
                llm_messages.append({"role": turn["role"], "content": turn["content"]})

            llm_messages = trim_messages_to_max_chars(
                llm_messages,
                self.config.max_prompt_chars,
            )

            try:
                reply_text = await generate_reply(
                    backend=cast(LLMBackend, self.config.llm_backend),
                    messages=llm_messages,
                    temperature=self.config.temperature,
                    top_p=self.config.top_p,
                    max_tokens=self.config.max_tokens,
                    ollama_url=self.config.ollama_url,
                    ollama_model=self.config.ollama_model,
                    openai_api_key=self.config.openai_api_key,
                    openai_model=self.config.openai_model,
                )
            except OllamaError as e:
                if str(e) == "Ollama returned empty content":
                    logger.error(
                        "Ollama returned no usable message.content (%s). "
                        "See preceding INFO log for raw JSON (check think/content).",
                        reason,
                    )
                else:
                    logger.error("Ollama failed (%s): %s", reason, e)
                return
            except OpenAIClientError as e:
                if str(e) == "OpenAI returned empty content":
                    logger.error("OpenAI returned no usable assistant content (%s).", reason)
                else:
                    logger.error("OpenAI failed (%s): %s", reason, e)
                return
            except Exception:
                logger.exception("Unexpected LLM error (%s)", reason)
                return

            if not reply_text:
                logger.warning("Empty reply from LLM; skipping send (%s)", reason)
                return

            reply_text = scrub_discord_mass_pings(reply_text)

            softened = apply_soft_reply_limit(reply_text, self.config.discord_reply_soft_limit)
            parts = split_text_for_discord(softened, self.config.discord_reply_hard_limit)
            if not parts:
                logger.warning("Reply empty after Discord shaping; skipping send (%s)", reason)
                return

            safe_mentions = discord.AllowedMentions(everyone=False, users=False, roles=False)

            try:
                for part in parts:
                    await message.channel.send(part, allowed_mentions=safe_mentions)
            except discord.DiscordException:
                logger.exception("Failed to send Discord message")
                return

            hist.append(
                {
                    "role": "assistant",
                    "content": build_assistant_message_wrapper(reply_text),
                }
            )
            self._last_reply_monotonic[ch_id] = time.monotonic()
            self._last_bot_text[ch_id] = reply_text
            if add_returning_hint:
                self._record_returning_user_greeting(ch_id, uid, time.monotonic())
            if reason in _FOLLOWUP_WINDOW_REFRESH_REASONS:
                self._refresh_inferred_followup_window(ch_id, uid, time.time())
            logger.info("Sent reply (%s, %d part(s)) in #%s", reason, len(parts), message.channel.name)

        finally:
            self._touch_user_channel_activity(ch_id, uid, now_wall)


async def run_bot(config: Config) -> None:
    """Construct the client and start the Discord connection."""
    client = SoppoBot(config)
    await client.start(config.discord_bot_token)


def run_sync(config: Config) -> None:
    """Entry from sync main: run the async bot until disconnect."""
    asyncio.run(run_bot(config))
