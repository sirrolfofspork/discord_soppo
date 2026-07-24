#!/usr/bin/env python3
"""Inspect/apply SOPPO memory review queue items.

Usage:
  .venv/bin/python tools/process_memory_review_queue.py --summary
  .venv/bin/python tools/process_memory_review_queue.py --apply-approved --summary
  .venv/bin/python tools/process_memory_review_queue.py --apply-approved --hot --summary

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
import subprocess
import sys
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from memory_extractor import StructuredMemoryStore  # noqa: E402
from memory_reviewer import apply_safe_candidate  # noqa: E402
from memory_store import load_memory_store, save_memory_store  # noqa: E402

SOPPO_DISCORD_SERVICE = "soppo-discord.service"


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


def load_queue(queue_path: Path) -> list[dict[str, Any]]:
    return _load_jsonl(queue_path)


def save_queue(queue_path: Path, items: list[dict[str, Any]]) -> None:
    _write_jsonl(queue_path, items)


def queue_status_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def filter_reviewable_items(
    items: list[dict[str, Any]],
    *,
    show_all: bool = False,
) -> list[dict[str, Any]]:
    if show_all:
        return list(items)
    return [item for item in items if item.get("status") == "pending"]


def apply_review_decisions(
    *,
    queue_path: Path,
    decisions: dict[str, str],
    reviewed_by: str = "web",
    now_iso: str | None = None,
) -> tuple[int, int]:
    """Update pending queue items to approved/rejected.

    Returns (updated_count, skipped_non_pending_count).
    """
    items = _load_jsonl(queue_path)
    now = now_iso or _utc_now()
    updated = 0
    skipped = 0
    for item in items:
        item_id = str(item.get("id", ""))
        decision = decisions.get(item_id)
        if decision not in {"approved", "rejected"}:
            continue
        if item.get("status") != "pending":
            skipped += 1
            continue
        item["status"] = decision
        review = item.setdefault("review", {})
        if isinstance(review, dict):
            review["reviewed_at"] = now
            review["reviewed_by"] = reviewed_by
        updated += 1
    if updated:
        _write_jsonl(queue_path, items)
    return updated, skipped


def _namespace_from_item(item: dict[str, Any]) -> tuple[str, ...] | None:
    raw = item.get("namespace")
    if not isinstance(raw, str) or not raw.strip():
        return None
    parts = tuple(part for part in raw.split("/") if part)
    return parts or None


def is_soppo_discord_service_active(
    *,
    is_active_runner: Callable[[], str] | None = None,
) -> bool:
    runner = is_active_runner or _default_is_active_runner
    return runner() == "active"


def _default_is_active_runner() -> str:
    completed = subprocess.run(
        ["systemctl", "--user", "is-active", SOPPO_DISCORD_SERVICE],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip()


def assert_safe_to_apply_memories(
    *,
    force: bool,
    hot: bool = False,
    is_active_runner: Callable[[], str] | None = None,
) -> str | None:
    if force or hot:
        return None
    if is_soppo_discord_service_active(is_active_runner=is_active_runner):
        return (
            f"{SOPPO_DISCORD_SERVICE} is active. Stop the bot before applying approved memories, "
            "pass --hot to rely on runtime disk refresh, or pass --force to override."
        )
    return None


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
    parser.add_argument(
        "--force",
        action="store_true",
        help="Apply approved memories even when soppo-discord.service is active.",
    )
    parser.add_argument(
        "--hot",
        action="store_true",
        help=(
            "Apply while soppo-discord.service is active and rely on the bot's "
            "runtime memory_store.json refresh before the next structured-memory retrieval."
        ),
    )
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    queue_path = Path(args.queue)
    memory_store_path = Path(args.memory_store)
    if args.apply_approved:
        warning = assert_safe_to_apply_memories(force=args.force, hot=args.hot)
        if warning:
            print(warning, file=sys.stderr)
            return 2
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
