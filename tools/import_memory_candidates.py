#!/usr/bin/env python3
"""Convert curated memory JSONL rows into a runtime memory review queue.

Reads human-curated import rows (id, category, memory_text, evidence, etc.) and
writes pending review-queue items compatible with tools/process_memory_review_queue.py.
Does not write to memory_store.json.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha1
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_NAMESPACE = "soppo/global/memories"
DEFAULT_SCOPE = "global"
DEFAULT_CONFIDENCE = 0.85
DEFAULT_IMPORTANCE = 0.6


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _clean_text(text: Any, *, max_len: int = 260) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 3].rstrip() + "..."
    return cleaned


def _text_hash(text: str) -> str:
    return sha1(text.encode("utf-8")).hexdigest()[:12]


def _stable_item_id(source_id: str, memory_text: str) -> str:
    return f"import_{source_id}_{_text_hash(memory_text)}"


def read_curated_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"input not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL at line {line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"line {line_no}: expected JSON object, got {type(row).__name__}")
            rows.append(row)
    return rows


def map_category_to_type(
    category: Any,
    *,
    user_id: int | None,
    type_override: str | None,
) -> str:
    if type_override:
        return type_override
    cat = str(category or "").strip().lower()
    if cat in {"identity", "character", "persona", "self", "boundary"}:
        return "character_note"
    if cat == "relationship":
        return "relationship_note"
    if cat == "preference":
        return "user_preference" if user_id is not None else "character_note"
    if cat in {"project", "world", "lore", "fact"}:
        return "project_fact"
    return "character_note"


def compute_confidence(
    importance_scores: Any,
    *,
    confidence_override: float | None,
) -> float:
    if confidence_override is not None:
        return max(0.0, min(1.0, confidence_override))
    if isinstance(importance_scores, dict):
        overall = importance_scores.get("overall")
        try:
            overall_val = float(overall)
        except (TypeError, ValueError):
            overall_val = None
        if overall_val is not None:
            return max(0.5, min(0.95, round(overall_val / 5.0, 2)))
    return DEFAULT_CONFIDENCE


def compute_importance(importance_scores: Any) -> float:
    if isinstance(importance_scores, dict):
        overall = importance_scores.get("overall")
        try:
            overall_val = float(overall)
        except (TypeError, ValueError):
            overall_val = None
        if overall_val is not None:
            return max(0.1, min(1.0, round(overall_val / 5.0, 2)))
    return DEFAULT_IMPORTANCE


def compact_evidence(evidence: Any, *, max_items: int = 2) -> list[dict[str, str]]:
    if not isinstance(evidence, list):
        return []
    compact: list[dict[str, str]] = []
    for entry in evidence[:max_items]:
        if not isinstance(entry, dict):
            continue
        item: dict[str, str] = {}
        source_file = entry.get("source_file")
        location = entry.get("location")
        if source_file:
            item["source_file"] = _clean_text(source_file, max_len=120)
        if location:
            item["location"] = _clean_text(location, max_len=120)
        if item:
            compact.append(item)
    return compact


def build_queue_item(
    row: dict[str, Any],
    *,
    namespace: str,
    scope: str,
    user_id: int | None,
    type_override: str | None,
    confidence_override: float | None,
    created_at: str,
) -> dict[str, Any]:
    source_id = str(row.get("id") or "").strip()
    if not source_id:
        raise ValueError("curated row missing required field: id")

    memory_text = _clean_text(row.get("memory_text"), max_len=1000)
    if not memory_text:
        raise ValueError(f"blank memory_text for source id {source_id!r}")

    memory_type = map_category_to_type(row.get("category"), user_id=user_id, type_override=type_override)
    candidate: dict[str, Any] = {
        "type": memory_type,
        "scope": scope,
        "text": memory_text,
        "importance": compute_importance(row.get("importance_scores")),
        "confidence": compute_confidence(row.get("importance_scores"), confidence_override=confidence_override),
    }
    if scope == "user":
        if user_id is None:
            raise ValueError(f"scope=user requires --user-id for source id {source_id!r}")
        candidate["user_id"] = user_id

    source_meta: dict[str, Any] = {
        "import": "curated_jsonl",
        "source_id": source_id,
        "category": row.get("category"),
        "reality": row.get("reality"),
        "sensitivity": row.get("sensitivity"),
        "source_count": row.get("source_count"),
        "evidence_count": row.get("evidence_count"),
        "evidence": compact_evidence(row.get("evidence")),
    }

    return {
        "id": _stable_item_id(source_id, memory_text),
        "status": "pending",
        "created_at": created_at,
        "candidate": candidate,
        "conflicts": [],
        "namespace": namespace,
        "source": source_meta,
        "review": {"reviewed_by": None, "reviewed_at": None, "notes": ""},
    }


def convert_rows(
    rows: list[dict[str, Any]],
    *,
    namespace: str,
    scope: str,
    user_id: int | None,
    type_override: str | None,
    confidence_override: float | None,
) -> list[dict[str, Any]]:
    created_at = _utc_now()
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in rows:
        item = build_queue_item(
            row,
            namespace=namespace,
            scope=scope,
            user_id=user_id,
            type_override=type_override,
            confidence_override=confidence_override,
            created_at=created_at,
        )
        item_id = str(item["id"])
        if item_id in seen_ids:
            raise ValueError(f"duplicate queue item id {item_id!r}; source rows must differ in id or memory_text")
        seen_ids.add(item_id)
        items.append(item)
    return items


def write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def summarize(items: list[dict[str, Any]]) -> str:
    by_type: dict[str, int] = {}
    for item in items:
        cand = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        memory_type = str(cand.get("type", "unknown"))
        by_type[memory_type] = by_type.get(memory_type, 0) + 1
    lines = [f"Converted {len(items)} curated row(s) to pending review queue item(s)."]
    for memory_type in sorted(by_type):
        lines.append(f"- {memory_type}: {by_type[memory_type]}")
    return "\n".join(lines)


def run_import(
    input_path: Path,
    output_path: Path,
    *,
    namespace: str,
    scope: str,
    user_id: int | None,
    type_override: str | None,
    confidence_override: float | None,
    force: bool,
    dry_run: bool,
) -> list[dict[str, Any]]:
    if output_path.exists() and not force and not dry_run:
        raise FileExistsError(
            f"output already exists: {output_path}. Pass --force to overwrite or choose another --output path."
        )

    rows = read_curated_jsonl(input_path)
    items = convert_rows(
        rows,
        namespace=namespace,
        scope=scope,
        user_id=user_id,
        type_override=type_override,
        confidence_override=confidence_override,
    )
    if not dry_run:
        write_jsonl(output_path, items)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert curated memory JSONL into a review queue.")
    parser.add_argument("input", help="Path to curated JSONL input")
    parser.add_argument(
        "--output",
        default=str(ROOT / "memory_review_queue.jsonl"),
        help="Review queue JSONL output path (default: memory_review_queue.jsonl)",
    )
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help=f"Target namespace (default: {DEFAULT_NAMESPACE})")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help=f"Candidate scope (default: {DEFAULT_SCOPE})")
    parser.add_argument("--user-id", type=int, default=None, help="Discord user id for user-scoped imports")
    parser.add_argument("--candidate-type", default=None, help="Override candidate.type for all rows")
    parser.add_argument("--confidence", type=float, default=None, help="Override candidate.confidence for all rows")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file")
    parser.add_argument("--dry-run", action="store_true", help="Validate/convert without writing output")
    args = parser.parse_args()

    try:
        items = run_import(
            Path(args.input),
            Path(args.output),
            namespace=args.namespace.strip(),
            scope=args.scope.strip(),
            user_id=args.user_id,
            type_override=args.candidate_type,
            confidence_override=args.confidence,
            force=args.force,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(summarize(items))
    if args.dry_run:
        print("(dry-run: no output written)")
    else:
        print(f"Wrote review queue: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
