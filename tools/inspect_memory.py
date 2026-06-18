#!/usr/bin/env python3
"""Inspect SOPPO's local JSON memory store without starting Discord.

This script intentionally prints only stored summary/memory records and health
metadata already present in memory_store.json. It does not connect to Discord or
call an LLM backend.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

SUSPICIOUS_IDENTITY_TERMS = ("tail", "fox", "ears", "furry", "kitsune")


def load_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"memory store not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit("memory store root is not a JSON object")
    return data


def shorten(text: object, limit: int = 220) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def is_summary_namespace(namespace: str) -> bool:
    return namespace.endswith("/summary")


def is_structured_memory_namespace(namespace: str) -> bool:
    return namespace.endswith("/memories")


def suspicious_terms(text: str) -> list[str]:
    lower = text.lower()
    return [term for term in SUSPICIOUS_IDENTITY_TERMS if term in lower]


def iter_records(store: dict[str, Any]):
    for namespace, records in sorted(store.items()):
        if not isinstance(records, dict):
            continue
        for key, record in sorted(records.items()):
            if isinstance(record, dict):
                yield namespace, key, record


def print_summary_records(store: dict[str, Any]) -> None:
    print("\n== Channel / DM summaries ==")
    found = False
    for namespace, key, record in iter_records(store):
        if not is_summary_namespace(namespace):
            continue
        found = True
        text = shorten(record.get("text", ""))
        health_keys = [
            "mode",
            "messages_since_regen",
            "pending_turn_count",
            "last_seen_message_time",
            "last_regen_wall",
            "last_regen_attempt",
            "last_regen_status",
            "last_regen_error",
            "cooldown_remaining_seconds",
        ]
        health = {k: record[k] for k in health_keys if k in record}
        print(f"- namespace: {namespace}")
        print(f"  key: {key}")
        print(f"  summary: {text or '(empty)'}")
        if health:
            print(f"  health: {json.dumps(health, sort_keys=True)}")
    if not found:
        print("- none")


def print_structured_memories(store: dict[str, Any]) -> None:
    print("\n== Structured memories ==")
    found = False
    type_counts: Counter[str] = Counter()
    suspicious: list[tuple[str, str, list[str], str]] = []
    stale_high_hit: list[tuple[str, str, int, str]] = []
    for namespace, key, record in iter_records(store):
        if not is_structured_memory_namespace(namespace):
            continue
        found = True
        memory_type = str(record.get("type", "memory"))
        text = str(record.get("text", ""))
        hits = int(record.get("hits", 0) or 0)
        type_counts[memory_type] += 1
        terms = suspicious_terms(text)
        if terms:
            suspicious.append((namespace, key, terms, shorten(text)))
        if hits >= 5:
            stale_high_hit.append((namespace, key, hits, shorten(text)))
        print(f"- namespace: {namespace}")
        print(f"  key: {key}")
        print(f"  type: {memory_type}")
        print(f"  hits: {hits}")
        print(f"  text: {shorten(text)}")
    if not found:
        print("- none")
        return
    print("\n== Structured memory counts ==")
    for memory_type, count in sorted(type_counts.items()):
        print(f"- {memory_type}: {count}")
    print("\n== Suspicious identity-term records ==")
    if suspicious:
        for namespace, key, terms, text in suspicious:
            print(f"- {namespace} / {key}: terms={','.join(terms)} text={text}")
    else:
        print("- none")
    print("\n== High-hit records to review ==")
    if stale_high_hit:
        for namespace, key, hits, text in sorted(stale_high_hit, key=lambda item: item[2], reverse=True):
            print(f"- {namespace} / {key}: hits={hits} text={text}")
    else:
        print("- none")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect SOPPO memory_store.json")
    parser.add_argument(
        "path",
        nargs="?",
        default="memory_store.json",
        help="Path to memory_store.json (default: ./memory_store.json)",
    )
    args = parser.parse_args()
    path = Path(args.path)
    store = load_store(path)
    namespace_count = len(store)
    record_count = sum(1 for _ in iter_records(store))
    print(f"memory_store: {path}")
    print(f"namespaces: {namespace_count}")
    print(f"records: {record_count}")
    print_summary_records(store)
    print_structured_memories(store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
