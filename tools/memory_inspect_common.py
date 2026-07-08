"""Shared helpers for offline memory_store.json inspection tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

SUSPICIOUS_IDENTITY_TERMS = ("tail", "fox", "ears", "furry", "kitsune")

BODY_CONTAMINATION_TERMS = (
    "robot body",
    "metal body",
    "biological body",
    "body status",
    "physical form",
)

SCENE_JOKE_RESIDUE_TERMS = (
    "joke",
    "roleplay",
    "scene",
    "pretend",
    "temporary",
)

DURABLE_FACT_TYPES = frozenset(
    {
        "character_note",
        "relationship_note",
        "project_fact",
        "server_fact",
    }
)


def load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"memory store not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("memory store root is not a JSON object")
    return data


def shorten(text: object, limit: int = 120) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def is_structured_memory_namespace(namespace: str) -> bool:
    return namespace.endswith("/memories")


def iter_records(store: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for namespace, records in sorted(store.items()):
        if not isinstance(records, dict):
            continue
        for key, record in sorted(records.items()):
            if isinstance(record, dict):
                yield namespace, key, record


def iter_structured_records(store: dict[str, Any]) -> Iterator[tuple[str, str, dict[str, Any]]]:
    for namespace, key, record in iter_records(store):
        if is_structured_memory_namespace(namespace):
            yield namespace, key, record


def matching_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    matched: list[str] = []
    for term in terms:
        if " " in term:
            if term in lower:
                matched.append(term)
        elif re.search(rf"\b{re.escape(term)}\b", lower):
            matched.append(term)
    return matched


def suspicious_identity_terms(text: str) -> list[str]:
    return matching_terms(text, SUSPICIOUS_IDENTITY_TERMS)


def suspicious_body_terms(text: str) -> list[str]:
    return matching_terms(text, BODY_CONTAMINATION_TERMS)
