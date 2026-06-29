#!/usr/bin/env python3
"""Inspect/apply SOPPO memory review queue items.

Usage:
  .venv/bin/python tools/process_memory_review_queue.py --summary
  .venv/bin/python tools/process_memory_review_queue.py --apply-approved --summary

Approve a queued item by editing memory_review_queue.jsonl and setting:
  "status": "approved"
Rejected items may be set to:
  "status": "rejected"
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory_extractor import StructuredMemoryStore  # noqa: E402
from memory_reviewer import apply_safe_candidate  # noqa: E402
from memory_store import load_memory_store, save_memory_store  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                items.append(item)
    return items


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def _namespace_from_item(item: dict[str, Any]) -> tuple[str, ...] | None:
    raw = item.get("namespace")
    if not isinstance(raw, str) or not raw.strip():
        return None
    parts = tuple(part for part in raw.split("/") if part)
    return parts or None


def apply_approved(*, queue_path: Path, memory_store_path: Path) -> tuple[int, list[str]]:
    items = _load_jsonl(queue_path)
    if not items:
        return 0, []
    store = StructuredMemoryStore(load_memory_store(memory_store_path))
    now = _utc_now()
    applied = 0
    errors: list[str] = []
    for item in items:
        if item.get("status") != "approved":
            continue
        candidate = item.get("candidate")
        namespace = _namespace_from_item(item)
        if not isinstance(candidate, dict) or namespace is None:
            item["status"] = "error"
            item.setdefault("review", {})["notes"] = "Invalid candidate or namespace."
            errors.append(str(item.get("id", "unknown")))
            continue
        try:
            key = apply_safe_candidate(candidate, store, namespace=namespace, now_iso=now)
        except Exception as exc:  # deliberate CLI guardrail
            item["status"] = "error"
            item.setdefault("review", {})["notes"] = f"Apply failed: {type(exc).__name__}"
            errors.append(str(item.get("id", "unknown")))
            continue
        item["status"] = "applied"
        item["applied_at"] = now
        item["applied_key"] = key
        applied += 1
    if applied:
        save_memory_store(memory_store_path, store.store)
    if applied or errors:
        _write_jsonl(queue_path, items)
    return applied, errors


def summarize_queue(queue_path: Path) -> str:
    items = _load_jsonl(queue_path)
    if not items:
        return "SOPPO memory review queue is empty."
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    pending = [item for item in items if item.get("status") == "pending"]
    lines = ["SOPPO memory review queue status:"]
    for status in sorted(counts):
        lines.append(f"- {status}: {counts[status]}")
    if pending:
        lines.append("")
        lines.append("Pending review items:")
        for item in pending[:10]:
            cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            conflicts = item.get("conflicts") if isinstance(item.get("conflicts"), list) else []
            conflict_kinds = ", ".join(str(c.get("kind")) for c in conflicts if isinstance(c, dict)) or "unspecified"
            lines.append(
                f"- {item.get('id')}: {cand.get('type')} / {cand.get('scope')} — {cand.get('text')} [conflicts: {conflict_kinds}]"
            )
        if len(pending) > 10:
            lines.append(f"- ...and {len(pending) - 10} more pending item(s).")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", default=str(ROOT / "memory_review_queue.jsonl"))
    parser.add_argument("--memory-store", default=str(ROOT / "memory_store.json"))
    parser.add_argument("--apply-approved", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    queue_path = Path(args.queue)
    memory_store_path = Path(args.memory_store)
    if args.apply_approved:
        applied, errors = apply_approved(queue_path=queue_path, memory_store_path=memory_store_path)
        if applied or errors:
            print(f"Applied approved memories: {applied}")
            if errors:
                print("Errors: " + ", ".join(errors))
    if args.summary or not args.apply_approved:
        print(summarize_queue(queue_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
