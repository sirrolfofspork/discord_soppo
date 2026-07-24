#!/usr/bin/env bash
# Review/apply SOPPO long-term memory queue items.
#
# Workflow:
#   1. Run this script to see pending queue items.
#   2. Edit memory_review_queue.jsonl and change wanted items from:
#        "status": "pending"
#      to:
#        "status": "approved"
#      or reject them with:
#        "status": "rejected"
#   3. Run this script again. Approved items are applied to memory_store.json.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"
QUEUE="$ROOT_DIR/memory_review_queue.jsonl"
STORE="$ROOT_DIR/memory_store.json"
TOOL="$ROOT_DIR/tools/process_memory_review_queue.py"

if [[ ! -x "$PYTHON" ]]; then
  echo "Could not find executable Python at: $PYTHON" >&2
  echo "Run this from the SOPPO repo after creating .venv, or fix the venv path." >&2
  exit 1
fi

if [[ ! -f "$TOOL" ]]; then
  echo "Could not find memory review tool at: $TOOL" >&2
  exit 1
fi

cd "$ROOT_DIR"

echo "SOPPO memory review"
echo "Repo:  $ROOT_DIR"
echo "Queue: $QUEUE"
echo "Store: $STORE"
echo

"$PYTHON" "$TOOL" --queue "$QUEUE" --memory-store "$STORE" --apply-approved --summary

echo
echo "Web review UI (pending items, approve/reject in browser):"
echo "  $PYTHON $ROOT_DIR/tools/serve_memory_review.py"
echo "Phone/home-network UI:"
echo "  $PYTHON $ROOT_DIR/tools/serve_memory_review.py --lan"
echo
echo "Hot-apply approved memories while SOPPO is running:"
echo "  $PYTHON $TOOL --queue $QUEUE --memory-store $STORE --apply-approved --hot --summary"
echo
echo "If there are pending items, use the web UI above or edit memory_review_queue.jsonl:"
echo "  pending  -> approved   to allow the memory"
echo "  pending  -> rejected   to reject it"
echo "Then run this script again. Tiny bureaucracy, but at least it has a button now."
