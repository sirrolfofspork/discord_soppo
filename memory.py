"""
Lightweight per-channel summary memory helpers.

This is deliberately deterministic and local: no vector database, embeddings, or
extra LLM calls. It condenses the oldest rolling-history turns into compact
bullets and leaves newer turns in normal recent history.
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
    """Turn a small batch of old chat turns into compact bullet-style memory."""
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
    when a rollover occurs.
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
        record = self.store.get_memory(self.namespace(guild_id=guild_id, channel_id=channel_id), "current")
        if not record:
            return ""
        text = record.get("text")
        return text if isinstance(text, str) else ""

    def set_summary(self, *, guild_id: int | None, channel_id: int, summary: str) -> None:
        clean = str(summary or "").strip()
        namespace = self.namespace(guild_id=guild_id, channel_id=channel_id)
        self.store.put_memory(namespace, "current", {"text": clean})


class PersistentChannelSummaryMemory(ChannelSummaryMemory):
    """Channel-summary memory that saves JSON after explicit writes."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        super().__init__(load_memory_store(self.path))

    def set_summary(self, *, guild_id: int | None, channel_id: int, summary: str) -> None:
        super().set_summary(guild_id=guild_id, channel_id=channel_id, summary=summary)
        save_memory_store(self.path, self.store)


def build_channel_summary_block(summary: str) -> str:
    """Format an optional channel-summary system context block."""
    clean = str(summary or "").strip()
    if not clean:
        return ""
    return "\n".join(
        [
            "[Channel summary memory]",
            "Earlier relevant context for this channel:",
            clean,
            "",
            "Use this for continuity only when relevant.",
            "Recent messages below are newer and should take priority.",
        ]
    ).strip()
