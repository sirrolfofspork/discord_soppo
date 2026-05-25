"""
Girls' Frontline lore snippets: keyword match → small context block for the LLM.

Actual lore lives in ``lore_store.json`` (edit by hand). This module only matches
and formats; it does not ship full canon text.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

# Cap how many entries we inject per message (keeps prompts small).
MAX_LORE_MATCHES = 3

_DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "lore_store.json"


def _alias_pattern(alias: str) -> re.Pattern[str]:
    """Whole-word / whole-phrase match, case-insensitive (multi-word: flexible spaces)."""
    tokens = alias.split()
    if not tokens:
        return re.compile(r"a^")  # never matches
    inner = r"\s+".join(re.escape(t) for t in tokens)
    return re.compile(rf"(?<!\w){inner}(?!\w)", flags=re.IGNORECASE)


@lru_cache(maxsize=256)
def _cached_alias_pattern(alias: str) -> re.Pattern[str]:
    return _alias_pattern(alias)


def find_relevant_lore(message_text: str, lore_store: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Scan ``message_text`` for aliases defined in ``lore_store``.

    Returns a list of match dicts (each includes ``id``, ``aliases``, ``summary``,
    ``soppo_take`` when present). Order follows first match in the store iteration;
    at most ``MAX_LORE_MATCHES`` entries.
    """
    if not message_text or not lore_store:
        return []

    text = message_text.strip()
    if not text:
        return []

    seen_ids: set[str] = set()
    matches: list[dict[str, Any]] = []

    for entry_id, raw in lore_store.items():
        if len(matches) >= MAX_LORE_MATCHES:
            break
        if not isinstance(raw, dict):
            continue
        aliases = raw.get("aliases")
        if not isinstance(aliases, list):
            continue

        hit = False
        for a in aliases:
            if not isinstance(a, str) or not a.strip():
                continue
            if _cached_alias_pattern(a).search(text):
                hit = True
                break

        if not hit:
            continue

        key = str(entry_id)
        if key in seen_ids:
            continue
        seen_ids.add(key)

        summary = raw.get("summary", "")
        soppo_take = raw.get("soppo_take", "")
        match: dict[str, Any] = {
            "id": key,
            "aliases": list(aliases) if isinstance(aliases, list) else [],
            "summary": summary if isinstance(summary, str) else str(summary),
            "soppo_take": soppo_take if isinstance(soppo_take, str) else str(soppo_take),
        }
        matches.append(match)

    return matches


def build_lore_context_block(matches: list[dict[str, Any]]) -> str:
    """
    Build a compact system-message-sized block from ``find_relevant_lore`` results.
    """
    if not matches:
        return ""

    lines: list[str] = [
        "[Relevant lore context]",
        "",
    ]
    for m in matches:
        lid = m.get("id", "?")
        summary = (m.get("summary") or "").strip()
        take = (m.get("soppo_take") or "").strip()
        lines.append(f"- {lid}")
        if summary:
            lines.append(f"  Summary: {summary}")
        if take:
            lines.append(f"  SOPPO angle: {take}")
        lines.append("")

    lines.extend(
        [
            "Use this naturally if relevant.",
            "Do not dump it all at once unless asked.",
        ]
    )
    return "\n".join(lines).strip()


def load_lore_store(path: Path | None = None) -> dict[str, Any]:
    """
    Load JSON lore definitions. Missing or invalid file → empty dict.
    """
    p = path or _DEFAULT_STORE_PATH
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError):
        return {}

    if isinstance(data, dict):
        return data
    return {}
