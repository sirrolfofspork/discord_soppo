"""API-assisted memory review with local conflict gates.

OpenAI/API models propose candidate memories. Local code validates them against
existing memory JSON and identity-contamination rules before anything is written.
Conflicting/risky candidates are appended to a JSONL review queue for SKK/Leva.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
import json
from pathlib import Path
import re
from typing import Any, Iterable, Literal, TypedDict, cast

from llm_client import LLMBackend, generate_reply
from memory_extractor import (
    StructuredMemoryStore,
    channel_memories_namespace,
    global_memories_namespace,
    guild_memories_namespace,
    user_memories_namespace,
)
from memory_store import Namespace, save_memory_store

MemoryReviewAction = Literal["apply", "queue", "drop"]

_ALLOWED_TYPES = {
    "running_joke",
    "user_preference",
    "relationship_note",
    "project_fact",
    "server_fact",
    "character_note",
}
_ALLOWED_SCOPES = {"user", "channel", "guild", "global"}
_IDENTITY_RISK_RE = re.compile(
    r"(?i)\b(soppo|sash|m4\s*sopmod|m4 sopmod ii)\b.*\b(is|am|are|becomes?|became|as)\b.*\b(leva|leva_v1|hermes|shadow|kanaya|vastra|karkat|phol|vampire|fox|kitsune|tail|ears)\b|"
    r"\b(leva|leva_v1|hermes|shadow|kanaya|vastra|karkat|phol)\b.*\b(is|am|are)\b.*\b(soppo|sash|m4\s*sopmod|m4 sopmod ii)\b"
)
_TEMPORARY_ROLEPLAY_RE = re.compile(
    r"(?i)\b(in this roleplay|for this scene|temporary roleplay|temporary scene|as a bit|for the bit|in the scene|pretend|rp only|roleplay only)\b"
)


class CandidateMemory(TypedDict, total=False):
    type: str
    scope: str
    text: str
    importance: float
    confidence: float
    user_id: int | str | None
    rationale: str


@dataclass(frozen=True)
class MemoryReviewResult:
    action: MemoryReviewAction
    candidate: dict[str, Any]
    conflicts: list[dict[str, Any]]
    namespace: Namespace | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_text(text: Any, *, max_len: int = 260) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    cleaned = cleaned.strip(" \t\r\n")
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3].rstrip() + "..."
    return cleaned


def _normalize(text: str) -> str:
    text = str(text).lower().replace("we're", "we are").replace("i'm", "i am")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def _jaccard(a: str, b: str) -> float:
    aa = set(_normalize(a).split())
    bb = set(_normalize(b).split())
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / len(aa | bb)


def _candidate_namespace(candidate: dict[str, Any], *, guild_id: int | None, channel_id: int) -> Namespace | None:
    scope = candidate.get("scope")
    if scope == "user":
        raw_user_id = candidate.get("user_id")
        try:
            user_id = int(raw_user_id) if raw_user_id is not None else None
        except (TypeError, ValueError):
            user_id = None
        if user_id is None:
            return None
        return user_memories_namespace(user_id)
    if scope == "guild":
        return guild_memories_namespace(guild_id)
    if scope == "global":
        return global_memories_namespace()
    if scope == "channel":
        return channel_memories_namespace(guild_id=guild_id, channel_id=channel_id)
    return None


def normalize_candidate(raw: dict[str, Any]) -> dict[str, Any] | None:
    memory_type = str(raw.get("type") or "").strip()
    scope = str(raw.get("scope") or "").strip()
    text = _clean_text(raw.get("text"))
    if memory_type not in _ALLOWED_TYPES or scope not in _ALLOWED_SCOPES or not text:
        return None
    try:
        importance = float(raw.get("importance", 0.6))
    except (TypeError, ValueError):
        importance = 0.6
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    candidate: dict[str, Any] = {
        "type": memory_type,
        "scope": scope,
        "text": text,
        "importance": max(0.1, min(1.0, importance)),
        "confidence": max(0.0, min(1.0, confidence)),
    }
    if scope == "user" and raw.get("user_id") is not None:
        try:
            candidate["user_id"] = int(cast(Any, raw.get("user_id")))
        except (TypeError, ValueError):
            return None
    rationale = _clean_text(raw.get("rationale"), max_len=180)
    if rationale:
        candidate["rationale"] = rationale
    return candidate


def build_memory_review_messages(*, current_summary: str, new_turns_text: str) -> list[dict[str, str]]:
    system = "\n".join(
        [
            "You are a neutral memory candidate reviewer for a Discord persona bot named SOPPO/Sash.",
            "You are not SOPPO and must not write in her voice.",
            "Return strict JSON only: {\"memories\": [...]} with no markdown.",
            "Allowed types: user_preference, relationship_note, project_fact, server_fact, running_joke, character_note.",
            "Allowed scopes: user, channel, guild, global. Use user scope only when a stable numeric user_id is visible.",
            "Extract only durable facts explicitly stated by users.",
            "Do not store temporary roleplay, quoted character dialogue, jokes as facts, or scene-only claims.",
            "Do not create memories that alter SOPPO/Sash identity, body, personality, husband/partner status, or canon unless SKK explicitly says it is durable canon.",
            "Each memory object must include: type, scope, text, importance, confidence, and user_id when scope=user.",
            "If no safe durable memories exist, return {\"memories\": []}.",
        ]
    )
    user = "\n".join(
        [
            "Existing neutral channel summary:",
            current_summary.strip() or "(none)",
            "",
            "New turns to review:",
            new_turns_text.strip() or "(none)",
        ]
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_memory_candidates(response_text: str) -> list[dict[str, Any]]:
    text = str(response_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    memories = payload.get("memories") if isinstance(payload, dict) else None
    if not isinstance(memories, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in memories:
        if isinstance(raw, dict):
            candidate = normalize_candidate(raw)
            if candidate is not None:
                normalized.append(candidate)
    return normalized[:10]


async def propose_memory_candidates_with_llm(
    *,
    backend: str,
    current_summary: str,
    new_turns_text: str,
    openai_api_key: str,
    openai_model: str,
    openai_timeout_seconds: float,
    ollama_url: str,
    ollama_model: str,
    lmstudio_base_url: str,
    lmstudio_api_key: str,
    lmstudio_model: str,
) -> list[dict[str, Any]]:
    if backend == "off":
        return []
    messages = build_memory_review_messages(current_summary=current_summary, new_turns_text=new_turns_text)
    response = await generate_reply(
        backend=cast(LLMBackend, backend),
        messages=messages,
        temperature=0.1,
        top_p=0.8,
        max_tokens=900,
        ollama_url=ollama_url,
        ollama_model=ollama_model,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        lmstudio_base_url=lmstudio_base_url,
        lmstudio_api_key=lmstudio_api_key,
        lmstudio_model=lmstudio_model,
        timeout_seconds=openai_timeout_seconds,
    )
    return parse_memory_candidates(response)


def _load_user_profile_conflict_texts(path: str | Path) -> list[dict[str, str]]:
    profile_path = Path(path)
    if not profile_path.exists():
        return []
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    out: list[dict[str, str]] = []
    for user_id, profile in data.items():
        if not isinstance(profile, dict):
            continue
        parts: list[str] = []
        for key in ("preferred_name", "username", "pronouns", "relationship"):
            value = profile.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(f"{key}: {value.strip()}")
        notes = profile.get("notes")
        if isinstance(notes, list):
            parts.extend(str(note).strip() for note in notes if str(note).strip())
        text = "; ".join(parts)
        if text:
            out.append({"user_id": str(user_id), "text": text})
    return out


def review_candidate_against_store(
    candidate: dict[str, Any],
    store: StructuredMemoryStore,
    *,
    guild_id: int | None,
    channel_id: int,
    user_profiles_path: str | Path = "user_profiles.json",
) -> MemoryReviewResult:
    namespace = _candidate_namespace(candidate, guild_id=guild_id, channel_id=channel_id)
    conflicts: list[dict[str, Any]] = []
    text = str(candidate.get("text", ""))
    norm = _normalize(text)
    if namespace is None:
        return MemoryReviewResult("queue", candidate, [{"kind": "invalid_scope", "detail": "missing/invalid namespace"}], None)
    if candidate.get("confidence", 0.0) < 0.7:
        conflicts.append({"kind": "low_confidence", "confidence": candidate.get("confidence")})
    if _TEMPORARY_ROLEPLAY_RE.search(text):
        return MemoryReviewResult("drop", candidate, [{"kind": "temporary_roleplay", "detail": "scene-only content"}], namespace)
    if _IDENTITY_RISK_RE.search(text):
        conflicts.append({"kind": "identity_risk", "detail": "candidate may alter or confuse SOPPO identity"})

    for profile in _load_user_profile_conflict_texts(user_profiles_path):
        profile_text = profile["text"]
        similarity = _jaccard(text, profile_text)
        if similarity >= 0.45:
            conflicts.append(
                {
                    "kind": "user_profile_overlap",
                    "similarity": round(similarity, 3),
                    "profile_user_id": profile.get("user_id"),
                    "profile_text": profile_text,
                }
            )

    for existing in store.list_memories(namespace):
        existing_text = str(existing.get("text", ""))
        if not existing_text:
            continue
        existing_norm = _normalize(existing_text)
        similarity = _jaccard(text, existing_text)
        if norm == existing_norm:
            return MemoryReviewResult("drop", candidate, [{"kind": "exact_duplicate", "existing_text": existing_text}], namespace)
        if similarity >= 0.72:
            conflicts.append(
                {
                    "kind": "possible_duplicate",
                    "similarity": round(similarity, 3),
                    "existing_type": existing.get("type"),
                    "existing_text": existing_text,
                }
            )
        elif candidate.get("type") == existing.get("type") and similarity >= 0.45:
            conflicts.append(
                {
                    "kind": "possible_conflict",
                    "similarity": round(similarity, 3),
                    "existing_type": existing.get("type"),
                    "existing_text": existing_text,
                }
            )

    if conflicts:
        return MemoryReviewResult("queue", candidate, conflicts, namespace)
    return MemoryReviewResult("apply", candidate, [], namespace)


def queue_review_item(
    path: str | Path,
    *,
    candidate: dict[str, Any],
    conflicts: list[dict[str, Any]],
    source: dict[str, Any],
    namespace: Namespace | None,
) -> str:
    queue_path = Path(path)
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    now = _utc_now()
    digest = sha1(json.dumps({"candidate": candidate, "source": source}, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    item_id = f"{now}_{digest}"
    item = {
        "id": item_id,
        "status": "pending",
        "created_at": now,
        "candidate": candidate,
        "conflicts": conflicts,
        "namespace": "/".join(namespace) if namespace else None,
        "source": source,
        "review": {"reviewed_by": None, "reviewed_at": None, "notes": ""},
    }
    with queue_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")
    return item_id


def apply_safe_candidate(
    candidate: dict[str, Any],
    store: StructuredMemoryStore,
    *,
    namespace: Namespace,
    now_iso: str,
) -> str:
    return store.upsert_memory(
        namespace,
        memory_type=str(candidate["type"]),
        text=str(candidate["text"]),
        importance=float(candidate.get("importance", 0.6)),
        now_iso=now_iso,
        source="api_memory_review",
    )


def process_memory_candidates(
    candidates: Iterable[dict[str, Any]],
    store: StructuredMemoryStore,
    *,
    memory_store_path: str | Path,
    review_queue_path: str | Path,
    user_profiles_path: str | Path = "user_profiles.json",
    guild_id: int | None = None,
    channel_id: int,
    source: dict[str, Any],
) -> dict[str, int]:
    stats = {"applied": 0, "queued": 0, "dropped": 0}
    now_iso = _utc_now()
    for candidate in candidates:
        review = review_candidate_against_store(
            candidate,
            store,
            guild_id=guild_id,
            channel_id=channel_id,
            user_profiles_path=user_profiles_path,
        )
        if review.action == "apply" and review.namespace is not None:
            apply_safe_candidate(candidate, store, namespace=review.namespace, now_iso=now_iso)
            stats["applied"] += 1
        elif review.action == "queue":
            queue_review_item(
                review_queue_path,
                candidate=candidate,
                conflicts=review.conflicts,
                source=source,
                namespace=review.namespace,
            )
            stats["queued"] += 1
        else:
            stats["dropped"] += 1
    if stats["applied"]:
        save_memory_store(memory_store_path, store.store)
    return stats


def load_pending_review_items(path: str | Path) -> list[dict[str, Any]]:
    queue_path = Path(path)
    if not queue_path.exists():
        return []
    items: list[dict[str, Any]] = []
    with queue_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("status") == "pending":
                items.append(item)
    return items
