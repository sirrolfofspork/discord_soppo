"""
Lightweight per-channel summary memory helpers.

The active runtime uses neutral LLM-generated channel summaries plus a very
small raw recent transcript. The older deterministic rollover helpers remain for
tests and compatibility with the existing structured-memory extraction seam.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Iterable

from memory_store import JsonMemoryStore, load_memory_store, save_memory_store

Turn = dict[str, str]


def _clean_one_line(text: str, *, max_len: int = 180) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def summarize_turns(turns: Iterable[Turn]) -> str:
    """Turn a small batch of chat turns into compact bullet-style text."""
    lines: list[str] = []
    for turn in turns:
        role = turn.get("role", "user")
        content = _clean_one_line(turn.get("content", ""))
        if not content:
            continue
        speaker = "SOPPO" if role == "assistant" else "User"
        if role == "user" and content.startswith("["):
            # User history is already wrapped as [Display Name]: message.
            lines.append(f"- {content}")
        else:
            lines.append(f"- {speaker}: {content}")
    return "\n".join(lines)


def _trim_summary(summary: str, max_chars: int) -> str:
    summary = summary.strip()
    if max_chars <= 0:
        return ""
    if len(summary) <= max_chars:
        return summary
    if max_chars <= 3:
        return summary[-max_chars:]
    return "..." + summary[-(max_chars - 3) :].lstrip()


def trim_neutral_summary(summary: str, max_chars: int) -> str:
    """Trim a generated neutral summary while preserving the newest content."""
    return _trim_summary(str(summary or ""), max_chars)


def build_neutral_summary_messages(
    *,
    current_summary: str,
    new_turns: Iterable[Turn],
    max_summary_chars: int,
) -> list[dict[str, str]]:
    """Build a neutral summarizer prompt without SOPPO's personality prompt."""
    turns_text = summarize_turns(new_turns) or "- No new substantive messages."
    existing = str(current_summary or "").strip() or "(none yet)"
    system = "\n".join(
        [
            "You are a neutral Discord conversation summarizer.",
            "Write compact factual bullets only.",
            "Include who said what, current topic, unresolved questions, and durable facts only when explicit.",
            "Running jokes clearly labeled as jokes may be included, but do not treat them as facts.",
            "Do not adopt roleplay claims as canon.",
            "You must not modify SOPPO identity, body, personality, or default character traits.",
            f"Keep the full summary under {max_summary_chars} characters.",
        ]
    )
    user = "\n".join(
        [
            "Existing neutral channel summary:",
            existing,
            "",
            "New messages to fold in:",
            turns_text,
            "",
            "Return only the updated neutral bullet summary.",
        ]
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def merge_channel_summary(
    current_summary: str,
    turns: Iterable[Turn],
    *,
    max_chars: int,
) -> str:
    """Merge newly summarized turns into the existing per-channel summary."""
    new_summary = summarize_turns(turns)
    pieces = [p.strip() for p in [current_summary, new_summary] if p and p.strip()]
    return _trim_summary("\n".join(pieces), max_chars)


def apply_summary_rollover(
    history: deque[Turn],
    *,
    current_summary: str,
    threshold: int,
    batch_size: int,
    max_summary_chars: int,
) -> tuple[str, int]:
    """
    If history is over threshold, summarize and remove the oldest batch.

    Returns (updated_summary, summarized_turn_count). Mutates ``history`` only
    when a rollover occurs. Kept for deterministic tests/backward compatibility;
    runtime neutral summaries do not expose long raw history to the prompt.
    """
    if threshold < 1 or batch_size < 1:
        return current_summary, 0
    if len(history) <= threshold:
        return current_summary, 0

    overflow = len(history) - threshold
    count = min(batch_size, overflow)
    if count <= 0:
        return current_summary, 0

    old_turns = [history.popleft() for _ in range(count)]
    summary = merge_channel_summary(
        current_summary,
        old_turns,
        max_chars=max_summary_chars,
    )
    return summary, count


class ChannelSummaryMemory:
    """Channel-summary facade backed by the generic JSON memory store."""

    def __init__(self, store: JsonMemoryStore) -> None:
        self.store = store

    @staticmethod
    def namespace(*, guild_id: int | None, channel_id: int) -> tuple[str, ...]:
        if guild_id is None:
            return ("discord", "dm", "channel", str(channel_id), "summary")
        return ("discord", "guild", str(guild_id), "channel", str(channel_id), "summary")

    def get_summary(self, *, guild_id: int | None, channel_id: int) -> str:
        record = self.get_summary_record(guild_id=guild_id, channel_id=channel_id)
        text = record.get("text")
        return text if isinstance(text, str) else ""

    def get_summary_record(self, *, guild_id: int | None, channel_id: int) -> dict[str, object]:
        record = self.store.get_memory(self.namespace(guild_id=guild_id, channel_id=channel_id), "current")
        return record if isinstance(record, dict) else {}

    def set_summary(self, *, guild_id: int | None, channel_id: int, summary: str) -> None:
        clean = str(summary or "").strip()
        namespace = self.namespace(guild_id=guild_id, channel_id=channel_id)
        self.store.put_memory(namespace, "current", {"text": clean})

    def set_neutral_summary(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        summary: str,
        last_regen_wall: float,
        messages_since_regen: int = 0,
    ) -> None:
        clean = str(summary or "").strip()
        namespace = self.namespace(guild_id=guild_id, channel_id=channel_id)
        record = dict(self.get_summary_record(guild_id=guild_id, channel_id=channel_id))
        record.update(
            {
                "text": clean,
                "mode": "neutral",
                "last_regen_wall": float(last_regen_wall),
                "messages_since_regen": int(messages_since_regen),
            }
        )
        self.store.put_memory(namespace, "current", record)

    def update_summary_metadata(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        **metadata: object,
    ) -> None:
        """Merge non-content health/debug metadata into the channel summary record."""
        namespace = self.namespace(guild_id=guild_id, channel_id=channel_id)
        record = dict(self.get_summary_record(guild_id=guild_id, channel_id=channel_id))
        for key, value in metadata.items():
            if key == "text":
                continue
            record[key] = value
        self.store.put_memory(namespace, "current", record)


class PersistentChannelSummaryMemory(ChannelSummaryMemory):
    """Channel-summary memory that saves JSON after explicit writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__(load_memory_store(self.path))

    def set_summary(self, *, guild_id: int | None, channel_id: int, summary: str) -> None:
        super().set_summary(guild_id=guild_id, channel_id=channel_id, summary=summary)
        save_memory_store(self.path, self.store)

    def set_neutral_summary(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        summary: str,
        last_regen_wall: float,
        messages_since_regen: int = 0,
    ) -> None:
        super().set_neutral_summary(
            guild_id=guild_id,
            channel_id=channel_id,
            summary=summary,
            last_regen_wall=last_regen_wall,
            messages_since_regen=messages_since_regen,
        )
        save_memory_store(self.path, self.store)

    def update_summary_metadata(
        self,
        *,
        guild_id: int | None,
        channel_id: int,
        **metadata: object,
    ) -> None:
        super().update_summary_metadata(guild_id=guild_id, channel_id=channel_id, **metadata)
        save_memory_store(self.path, self.store)


def build_channel_summary_block(summary: str) -> str:
    """Format an optional channel-summary system context block."""
    clean = str(summary or "").strip()
    if not clean:
        return ""
    return "\n".join(
        [
            "[Channel neutral summary]",
            "Neutral earlier context for this channel:",
            clean,
            "",
            "Use this only as background continuity when the newest live message clearly needs it.",
            "Do not answer, continue, or re-raise every bullet in this summary.",
            "If the newest live message changes topic, ignore stale summary details.",
            "Recent raw messages below are newer and should take priority.",
        ]
    ).strip()
