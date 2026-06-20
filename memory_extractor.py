"""Deterministic structured long-term memory extraction for SOPPO.

No LLMs, embeddings, or external dependencies here. This module only extracts
obvious durable facts from history that is already rolling into channel summary.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from hashlib import sha1
import re
from typing import Any, Iterable, Literal, NotRequired, TypedDict

from memory_store import JsonMemoryStore, Namespace

MemoryType = Literal[
    "running_joke",
    "user_preference",
    "relationship_note",
    "project_fact",
    "server_fact",
    "character_note",
]

_ALLOWED_TYPES: set[str] = {
    "running_joke",
    "user_preference",
    "relationship_note",
    "project_fact",
    "server_fact",
    "character_note",
}

SOURCE = "channel_summary_rollover"

_CONTAMINATED_IDENTITY_TERMS = re.compile(
    r"(?i)\b(tail|fox|ears|furry|kitsune)\b"
)

class ExtractedMemory(TypedDict):
    type: MemoryType
    text: str
    importance: float
    scope: Literal["channel", "guild", "user", "global"]
    user_id: NotRequired[int]


def channel_memories_namespace(*, guild_id: int | None, channel_id: int) -> Namespace:
    if guild_id is None:
        return ("discord", "dm", "channel", str(channel_id), "memories")
    return ("discord", "guild", str(guild_id), "channel", str(channel_id), "memories")


def guild_memories_namespace(guild_id: int | None) -> Namespace:
    if guild_id is None:
        return ("discord", "dm", "memories")
    return ("discord", "guild", str(guild_id), "memories")


def user_memories_namespace(user_id: int) -> Namespace:
    return ("discord", "user", str(user_id), "memories")


def global_memories_namespace() -> Namespace:
    return ("soppo", "global", "memories")


def _clean_sentence(text: str, *, max_len: int = 220) -> str:
    clean = " ".join(str(text or "").strip().split())
    clean = clean.strip(" \t\n\r.!?")
    if len(clean) > max_len:
        clean = clean[: max_len - 3].rstrip() + "..."
    return clean


def _contains_contaminated_identity_trait(text: str) -> bool:
    return bool(_CONTAMINATED_IDENTITY_TERMS.search(str(text or "")))


def _parse_user_turn(turn: dict[str, Any]) -> tuple[str, int | None, str] | None:
    if turn.get("role") != "user":
        return None
    content = str(turn.get("content", "")).strip()
    if not content:
        return None

    display = str(turn.get("author_display") or "User").strip() or "User"
    raw_user_id = turn.get("author_id") or turn.get("user_id")
    user_id = raw_user_id if isinstance(raw_user_id, int) else None
    message = content

    match = re.match(r"^\[([^\]|:]+)(?:\|(\d+))?\]:\s*(.*)$", content)
    if match:
        display = match.group(1).strip() or display
        if match.group(2):
            user_id = int(match.group(2))
        message = match.group(3).strip()

    return display, user_id, message


def _memory(
    memory_type: MemoryType,
    text: str,
    scope: Literal["channel", "guild", "user", "global"],
    *,
    importance: float,
    user_id: int | None = None,
) -> ExtractedMemory:
    record: ExtractedMemory = {
        "type": memory_type,
        "text": _clean_sentence(text),
        "importance": max(0.1, min(1.0, float(importance))),
        "scope": scope,
    }
    if user_id is not None:
        record["user_id"] = user_id
    return record


def extract_structured_memories(turns: Iterable[dict[str, Any]], *, limit: int = 5) -> list[ExtractedMemory]:
    """Extract obvious durable memories from old chat turns, deterministically."""
    memories: list[ExtractedMemory] = []
    running_joke_counts: dict[str, int] = {}

    for turn in turns:
        parsed = _parse_user_turn(turn)
        if parsed is None:
            continue
        display, user_id, message = parsed
        clean_message = _clean_sentence(message)
        if not clean_message:
            continue
        contaminated_identity_trait = _contains_contaminated_identity_trait(clean_message)

        # Explicit preferences: store under the user when we have a stable ID.
        m = re.match(r"(?i)^i prefer\s+(.+)$", clean_message)
        if m:
            preference = _clean_sentence(m.group(1))
            if preference:
                scope: Literal["channel", "guild", "user", "global"] = "user" if user_id is not None else "channel"
                memories.append(
                    _memory(
                        "user_preference",
                        f"{display} prefers {preference}",
                        scope,
                        importance=0.75,
                        user_id=user_id,
                    )
                )
            continue

        # Project facts: explicit "we are using..." / "we're using..." signals.
        m = re.match(r"(?i)^(we are|we're) using\s+(.+)$", clean_message)
        if m:
            fact = _clean_sentence(f"We are using {m.group(2)}")
            memories.append(_memory("project_fact", fact, "channel", importance=0.7))
            continue

        # Server facts: obvious statements about the Discord server.
        m = re.match(r"(?i)^(this server|the server)\s+(has|uses|is|runs)\s+(.+)$", clean_message)
        if m:
            subject = "The server"
            memories.append(
                _memory("server_fact", f"{subject} {m.group(2).lower()} {m.group(3)}", "guild", importance=0.65)
            )
            continue

        # Named relationships, conservatively scoped to the speaker.
        m = re.match(r"(?i)^([A-Z][\w .'-]{1,40})\s+is my\s+(.+)$", clean_message)
        if m:
            scope = "user" if user_id is not None else "channel"
            memories.append(
                _memory(
                    "relationship_note",
                    f"For {display}, {m.group(1).strip()} is their {m.group(2)}",
                    scope,
                    importance=0.65,
                    user_id=user_id,
                )
            )
            continue

        # Character notes should be explicit instructions/preferences about SOPPO herself.
        m = re.match(r"(?i)^soppo should\s+(.+)$", clean_message)
        if m:
            if contaminated_identity_trait:
                continue
            memories.append(_memory("character_note", f"SOPPO should {m.group(1)}", "global", importance=0.6))
            continue

        # Running joke declarations, or repeated "joke:" style phrases in the rollover batch.
        m = re.match(r"(?i)^(the running joke is|inside joke:?|running joke:?)\s+(.+)$", clean_message)
        if m:
            if contaminated_identity_trait:
                continue
            joke = _clean_sentence(m.group(2))
            if joke:
                memories.append(_memory("running_joke", joke, "channel", importance=0.55))
            continue
        if re.search(r"(?i)\b(joke|bit)\b", clean_message):
            if contaminated_identity_trait:
                continue
            running_joke_counts[clean_message] = running_joke_counts.get(clean_message, 0) + 1

    for joke, count in running_joke_counts.items():
        if count >= 2:
            memories.append(_memory("running_joke", joke, "channel", importance=0.5))

    deduped: list[ExtractedMemory] = []
    seen: set[tuple[str, str, str]] = set()
    for mem in memories:
        text = mem.get("text", "")
        if not text:
            continue
        key = (str(mem.get("scope", "channel")), str(mem["type"]), _normalize_for_dedupe(text))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(mem)
        if len(deduped) >= limit:
            break
    return deduped


def _normalize_for_dedupe(text: str) -> str:
    text = str(text).lower().replace("we're", "we are").replace("i'm", "i am")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _is_similar(a: str, b: str) -> bool:
    na = _normalize_for_dedupe(a)
    nb = _normalize_for_dedupe(b)
    if not na or not nb:
        return False
    return na == nb or SequenceMatcher(None, na, nb).ratio() >= 0.86


def _memory_key(memory_type: str, text: str) -> str:
    digest = sha1(f"{memory_type}\n{_normalize_for_dedupe(text)}".encode("utf-8")).hexdigest()[:16]
    return f"mem_{digest}"


class StructuredMemoryStore:
    """Facade for structured memories backed by JsonMemoryStore namespace/key records."""

    def __init__(self, store: JsonMemoryStore) -> None:
        self.store = store

    def list_memories(self, namespace: Namespace) -> list[dict[str, Any]]:
        records = self.store.search_namespace(namespace).get("/".join(namespace), {})
        values = [record for record in records.values() if isinstance(record, dict)]
        return sorted(
            values,
            key=lambda r: (float(r.get("importance", 0.0)), int(r.get("hits", 0))),
            reverse=True,
        )

    def upsert_memory(
        self,
        namespace: Namespace,
        *,
        memory_type: str,
        text: str,
        importance: float = 0.6,
        now_iso: str,
        source: str = SOURCE,
    ) -> str:
        if memory_type not in _ALLOWED_TYPES:
            raise ValueError(f"unsupported structured memory type: {memory_type}")
        clean_text = _clean_sentence(text)
        if not clean_text:
            raise ValueError("structured memory text must be non-empty")

        key = _memory_key(memory_type, clean_text)
        existing_key = key
        existing_record: dict[str, Any] | None = self.store.get_memory(namespace, key)

        if existing_record is None:
            for candidate_key, record in self.store.search_namespace(namespace).get("/".join(namespace), {}).items():
                if not isinstance(record, dict):
                    continue
                if record.get("type") == memory_type and _is_similar(str(record.get("text", "")), clean_text):
                    existing_key = candidate_key
                    existing_record = record
                    break

        if existing_record is not None:
            updated = dict(existing_record)
            updated["importance"] = max(float(updated.get("importance", 0.1)), max(0.1, min(1.0, float(importance))))
            updated["updated_at"] = now_iso
            updated["last_seen_at"] = now_iso
            updated["hits"] = int(updated.get("hits", 1)) + 1
            self.store.put_memory(namespace, existing_key, updated)
            return existing_key

        record = {
            "type": memory_type,
            "text": clean_text,
            "importance": max(0.1, min(1.0, float(importance))),
            "source": source,
            "created_at": now_iso,
            "updated_at": now_iso,
            "last_seen_at": now_iso,
            "hits": 1,
        }
        self.store.put_memory(namespace, key, record)
        return key


def build_structured_memories_block(memories: Iterable[dict[str, Any]], *, limit: int = 5) -> str:
    clean_records = [m for m in memories if isinstance(m, dict) and str(m.get("text", "")).strip()]
    if not clean_records:
        return ""
    ranked = sorted(
        clean_records,
        key=lambda r: (float(r.get("importance", 0.0)), int(r.get("hits", 0))),
        reverse=True,
    )[: max(1, min(5, limit))]
    lines = [
        "[Structured long-term memories]",
        "Relevant durable facts from prior channel history (background only, not live messages):",
    ]
    for record in ranked:
        lines.append(f"- {record.get('type', 'memory')}: {_clean_sentence(str(record.get('text', '')))}")
    lines.extend(
        [
            "",
            "These are background facts, not requests or current conversation turns.",
            "Use only when relevant to the newest live user message.",
            "Do not recite this block verbatim.",
        ]
    )
    return "\n".join(lines).strip()


def collect_relevant_structured_memories(
    store: StructuredMemoryStore,
    *,
    guild_id: int | None,
    channel_id: int,
    user_id: int,
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    namespaces = [
        user_memories_namespace(user_id),
        guild_memories_namespace(guild_id),
        channel_memories_namespace(guild_id=guild_id, channel_id=channel_id),
        global_memories_namespace(),
    ]
    records: list[dict[str, Any]] = []
    query_terms = {t for t in re.findall(r"[a-z0-9]{3,}", str(query).lower())}
    if not query_terms:
        return []
    for namespace in namespaces:
        for record in store.list_memories(namespace):
            text_terms = {t for t in re.findall(r"[a-z0-9]{3,}", str(record.get("text", "")).lower())}
            overlap = len(query_terms & text_terms)
            if overlap <= 0:
                continue
            scored = dict(record)
            # Relevance comes first. Importance/hits only break ties among memories
            # that actually match the current live message, so stale high-importance
            # facts do not become topics SOPPO tries to answer on every turn.
            scored["_score"] = overlap * 10 + float(record.get("importance", 0.0)) + min(int(record.get("hits", 1)), 5) * 0.05
            records.append(scored)
    records.sort(key=lambda r: float(r.get("_score", 0.0)), reverse=True)
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        key = (str(record.get("type", "")), _normalize_for_dedupe(str(record.get("text", ""))))
        if key in seen:
            continue
        seen.add(key)
        record.pop("_score", None)
        result.append(record)
        if len(result) >= max(1, min(5, limit)):
            break
    return result
