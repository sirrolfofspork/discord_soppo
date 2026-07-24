import json
import tempfile
import unittest
from pathlib import Path


def _write_queue(path: Path, items: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")


def _sample_pending(item_id: str = "pending-1") -> dict:
    return {
        "id": item_id,
        "status": "pending",
        "namespace": "soppo/global/memories",
        "created_at": "2026-07-24T12:00:00Z",
        "candidate": {
            "type": "project_fact",
            "scope": "global",
            "text": "Test memory text",
            "confidence": 0.8,
            "importance": 0.7,
        },
        "conflicts": [{"kind": "low_confidence", "confidence": 0.5}],
        "review": {"notes": "", "reviewed_at": None, "reviewed_by": None},
    }


class ServeMemoryReviewLogicTests(unittest.TestCase):
    def test_parse_review_submission(self):
        from tools.serve_memory_review import parse_review_submission

        body = b"decision_a=approve&decision_b=reject&ignore=1"
        self.assertEqual(
            parse_review_submission(body),
            {"a": "approved", "b": "rejected"},
        )

    def test_filter_reviewable_items_hides_non_pending_by_default(self):
        from tools.process_memory_review_queue import filter_reviewable_items

        items = [
            _sample_pending("p1"),
            {"id": "a1", "status": "approved"},
            {"id": "r1", "status": "rejected"},
        ]
        pending_only = filter_reviewable_items(items, show_all=False)
        self.assertEqual([item["id"] for item in pending_only], ["p1"])
        self.assertEqual(len(filter_reviewable_items(items, show_all=True)), 3)

    def test_apply_review_decisions_updates_pending_only(self):
        from tools.process_memory_review_queue import apply_review_decisions, load_queue

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "queue.jsonl"
            _write_queue(
                queue_path,
                [
                    _sample_pending("p1"),
                    _sample_pending("p2"),
                    {"id": "done", "status": "approved", "review": {}},
                ],
            )
            updated, skipped = apply_review_decisions(
                queue_path=queue_path,
                decisions={"p1": "approved", "done": "rejected"},
                reviewed_by="test-reviewer",
                now_iso="2026-07-24T12:00:00Z",
            )
            self.assertEqual(updated, 1)
            self.assertEqual(skipped, 1)
            items = load_queue(queue_path)
            by_id = {item["id"]: item for item in items}
            self.assertEqual(by_id["p1"]["status"], "approved")
            self.assertEqual(by_id["p1"]["review"]["reviewed_by"], "test-reviewer")
            self.assertEqual(by_id["p1"]["review"]["reviewed_at"], "2026-07-24T12:00:00Z")
            self.assertEqual(by_id["p2"]["status"], "pending")
            self.assertEqual(by_id["done"]["status"], "approved")

    def test_render_index_page_escapes_html(self):
        from tools.serve_memory_review import render_index_page

        items = [
            {
                "id": "x1",
                "status": "pending",
                "namespace": "test",
                "created_at": "now",
                "candidate": {
                    "type": "note",
                    "scope": "global",
                    "text": '<script>alert("x")</script>',
                    "confidence": 0.5,
                    "importance": 0.5,
                },
                "conflicts": [],
            }
        ]
        html = render_index_page(items=items, show_all=False)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert", html)

    def test_render_index_page_default_hides_non_pending(self):
        from tools.serve_memory_review import render_index_page

        items = [
            _sample_pending("p1"),
            {"id": "old", "status": "rejected", "candidate": {"text": "hidden"}},
        ]
        html = render_index_page(items=items, show_all=False)
        self.assertIn("p1", html)
        self.assertNotIn(">old<", html)

    def test_access_urls_for_localhost(self):
        from tools.serve_memory_review import access_urls

        self.assertEqual(access_urls(host="127.0.0.1", port=8765), ["http://127.0.0.1:8765/"])

    def test_access_urls_for_lan_bind_includes_loopback_and_discovered_lan(self):
        from unittest import mock
        from tools import serve_memory_review

        with mock.patch.object(serve_memory_review, "discover_lan_addresses", return_value=["192.168.1.44"]):
            self.assertEqual(
                serve_memory_review.access_urls(host="0.0.0.0", port=8765),
                ["http://127.0.0.1:8765/", "http://192.168.1.44:8765/"],
            )

    def test_run_apply_blocked_when_service_active(self):
        from tools.serve_memory_review import run_apply_approved

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "queue.jsonl"
            store_path = Path(tmp) / "memory_store.json"
            store_path.write_text("{}", encoding="utf-8")
            _write_queue(queue_path, [])

            ok, message = run_apply_approved(
                queue_path=queue_path,
                memory_store_path=store_path,
                force=False,
                is_active_runner=lambda: "active",
            )
            self.assertFalse(ok)
            self.assertIn("soppo-discord.service", message)

    def test_run_apply_hot_allowed_when_service_active(self):
        from memory import PersistentChannelSummaryMemory
        from memory_extractor import global_memories_namespace
        from tools.process_memory_review_queue import load_queue
        from tools.serve_memory_review import run_apply_approved

        with tempfile.TemporaryDirectory() as tmp:
            queue_path = Path(tmp) / "queue.jsonl"
            store_path = Path(tmp) / "memory_store.json"
            store_path.write_text("{}", encoding="utf-8")
            _write_queue(
                queue_path,
                [
                    {
                        "id": "approved-hot",
                        "status": "approved",
                        "namespace": "soppo/global/memories",
                        "candidate": {
                            "type": "project_fact",
                            "scope": "global",
                            "text": "Hot apply memory is visible without restart",
                            "confidence": 0.9,
                            "importance": 0.8,
                        },
                        "review": {},
                    }
                ],
            )

            runtime_memory = PersistentChannelSummaryMemory(store_path)
            ok, message = run_apply_approved(
                queue_path=queue_path,
                memory_store_path=store_path,
                hot=True,
                is_active_runner=lambda: "active",
            )
            runtime_memory.reload_from_disk()
            visible = runtime_memory.store.search_namespace(global_memories_namespace())
            queue_items = load_queue(queue_path)

            self.assertTrue(ok)
            self.assertIn("Applied 1 approved item(s).", message)
            self.assertEqual(queue_items[0]["status"], "applied")
            self.assertTrue(
                any(
                    record.get("text") == "Hot apply memory is visible without restart"
                    for records in visible.values()
                    for record in records.values()
                )
            )


if __name__ == "__main__":
    unittest.main()
