#!/usr/bin/env python3
"""Review-only scan of structured memories for pruning/quarantine candidates.

This tool reads memory_store.json and flags records for human review. It never
deletes, modifies, quarantines, or writes back to the store.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.memory_inspect_common import (  # noqa: E402
    DURABLE_FACT_TYPES,
    SCENE_JOKE_RESIDUE_TERMS,
    iter_structured_records,
    load_store,
    matching_terms,
    shorten,
    suspicious_body_terms,
    suspicious_identity_terms,
)

REVIEW_BANNER = (
    "REVIEW ONLY: no changes were written to memory_store.json or any other file."
)

STALE_RELATIONSHIP_DAYS = 180
HIGH_HIT_GENERIC_THRESHOLD = 5
HIGH_HIT_GENERIC_MAX_CHARS = 50
HIGH_HIT_REVIEW_THRESHOLD = 10
SIMILARITY_RATIO = 0.86


def normalize_for_dedupe(text: str) -> str:
    import re

    text = str(text).lower().replace("we're", "we are").replace("i'm", "i am")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def is_similar(a: str, b: str) -> bool:
    na = normalize_for_dedupe(a)
    nb = normalize_for_dedupe(b)
    if not na or not nb:
        return False
    return na == nb or SequenceMatcher(None, na, nb).ratio() >= SIMILARITY_RATIO


def parse_iso_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def record_timestamp(record: dict[str, Any]) -> datetime | None:
    for field in ("updated_at", "created_at"):
        parsed = parse_iso_timestamp(record.get(field))
        if parsed is not None:
            return parsed
    return None


def build_candidate(
    namespace: str,
    key: str,
    record: dict[str, Any],
    reasons: list[str],
    *,
    text_preview_limit: int = 120,
) -> dict[str, Any]:
    return {
        "namespace": namespace,
        "key": key,
        "type": str(record.get("type", "memory")),
        "hits": int(record.get("hits", 0) or 0),
        "reasons": sorted(set(reasons)),
        "text_preview": shorten(record.get("text", ""), text_preview_limit),
    }


def find_duplicate_flags(
    records: list[tuple[str, str, dict[str, Any]]],
) -> dict[tuple[str, str], list[str]]:
    flags: dict[tuple[str, str], list[str]] = defaultdict(list)

    by_namespace: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    for item in records:
        by_namespace[item[0]].append(item)

    for namespace, namespace_records in by_namespace.items():
        for idx, (ns_a, key_a, record_a) in enumerate(namespace_records):
            text_a = str(record_a.get("text", ""))
            for ns_b, key_b, record_b in namespace_records[idx + 1 :]:
                text_b = str(record_b.get("text", ""))
                if is_similar(text_a, text_b):
                    flags[(ns_a, key_a)].append("duplicate_namespace")
                    flags[(ns_b, key_b)].append("duplicate_namespace")

    for idx, (ns_a, key_a, record_a) in enumerate(records):
        text_a = str(record_a.get("text", ""))
        for ns_b, key_b, record_b in records[idx + 1 :]:
            if ns_a == ns_b:
                continue
            text_b = str(record_b.get("text", ""))
            if is_similar(text_a, text_b):
                flags[(ns_a, key_a)].append("duplicate_global")
                flags[(ns_b, key_b)].append("duplicate_global")

    return flags


def scan_store(
    store: dict[str, Any],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    reference = now or datetime.now(timezone.utc)
    stale_cutoff = reference - timedelta(days=STALE_RELATIONSHIP_DAYS)

    structured = list(iter_structured_records(store))
    duplicate_flags = find_duplicate_flags(structured)

    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    reason_lists: dict[tuple[str, str], list[str]] = defaultdict(list)

    for namespace, key, record in structured:
        item_key = (namespace, key)
        text = str(record.get("text", ""))
        memory_type = str(record.get("type", "memory"))
        hits = int(record.get("hits", 0) or 0)
        reasons = reason_lists[item_key]

        reasons.extend(duplicate_flags.get(item_key, []))

        identity_terms = suspicious_identity_terms(text)
        if identity_terms:
            reasons.append("identity_contamination")

        body_terms = suspicious_body_terms(text)
        if body_terms:
            reasons.append("body_contamination")

        if memory_type == "relationship_note":
            timestamp = record_timestamp(record)
            if hits <= 1 or (timestamp is not None and timestamp < stale_cutoff):
                reasons.append("stale_relationship")

        normalized_len = len(normalize_for_dedupe(text))
        if hits >= HIGH_HIT_GENERIC_THRESHOLD and normalized_len <= HIGH_HIT_GENERIC_MAX_CHARS:
            reasons.append("high_hit_generic")
        elif hits >= HIGH_HIT_REVIEW_THRESHOLD:
            reasons.append("high_hit_review")

        if memory_type in DURABLE_FACT_TYPES and matching_terms(text, SCENE_JOKE_RESIDUE_TERMS):
            reasons.append("scene_joke_residue")

        if reasons:
            candidates[item_key] = build_candidate(namespace, key, record, reasons)

    return sorted(
        candidates.values(),
        key=lambda item: (item["namespace"], item["key"]),
    )


def counts_by_reason(candidates: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for candidate in candidates:
        for reason in candidate.get("reasons", []):
            counts[str(reason)] += 1
    return dict(sorted(counts.items()))


def format_text_report(
    *,
    store_path: Path,
    candidates: list[dict[str, Any]],
) -> str:
    lines = [
        REVIEW_BANNER,
        f"store: {store_path}",
        f"candidates: {len(candidates)}",
    ]
    reason_counts = counts_by_reason(candidates)
    lines.append("counts_by_reason:")
    if reason_counts:
        for reason, count in reason_counts.items():
            lines.append(f"  - {reason}: {count}")
    else:
        lines.append("  - none")

    lines.append("candidate_lines:")
    if not candidates:
        lines.append("  - none")
    else:
        for candidate in candidates:
            reasons = ",".join(candidate["reasons"])
            lines.append(
                "  - "
                f"{candidate['namespace']} / {candidate['key']} "
                f"type={candidate['type']} hits={candidate['hits']} "
                f"reasons={reasons} text={candidate['text_preview']}"
            )
    return "\n".join(lines)


def run_review(store_path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    store = load_store(store_path)
    candidates = scan_store(store, now=now)
    return {
        "review_only": True,
        "no_changes_written": True,
        "store_path": str(store_path),
        "candidate_count": len(candidates),
        "counts_by_reason": counts_by_reason(candidates),
        "candidates": candidates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review-only scan for memory pruning/quarantine candidates",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="memory_store.json",
        help="Path to memory_store.json (default: ./memory_store.json)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON on stdout",
    )
    args = parser.parse_args(argv)
    store_path = Path(args.path)

    try:
        report = run_review(store_path)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"invalid memory store: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            format_text_report(
                store_path=store_path,
                candidates=report["candidates"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
