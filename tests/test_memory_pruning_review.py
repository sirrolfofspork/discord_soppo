import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _write_store(path: Path, store: dict) -> None:
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def _synthetic_fixture_store() -> dict:
    return {
        "soppo/global/memories": {
            "mem_dup_a": {
                "type": "project_fact",
                "text": "Fixture alpha uses LM Studio locally",
                "hits": 2,
                "created_at": "2026-06-01T12:00:00Z",
                "updated_at": "2026-06-01T12:00:00Z",
            },
            "mem_dup_b": {
                "type": "project_fact",
                "text": "Fixture alpha uses lm studio locally",
                "hits": 1,
                "created_at": "2026-06-02T12:00:00Z",
                "updated_at": "2026-06-02T12:00:00Z",
            },
            "mem_identity": {
                "type": "character_note",
                "text": "Synthetic note claims SOPPO has fox ears today",
                "hits": 1,
                "created_at": "2026-06-03T12:00:00Z",
                "updated_at": "2026-06-03T12:00:00Z",
            },
            "mem_body": {
                "type": "character_note",
                "text": "Synthetic claim about a robot body replacement arc",
                "hits": 1,
                "created_at": "2026-06-04T12:00:00Z",
                "updated_at": "2026-06-04T12:00:00Z",
            },
            "mem_high_hit": {
                "type": "project_fact",
                "text": "Short generic note",
                "hits": 8,
                "created_at": "2026-06-05T12:00:00Z",
                "updated_at": "2026-06-05T12:00:00Z",
            },
            "mem_scene": {
                "type": "relationship_note",
                "text": "Temporary scene joke where Victor is my husband",
                "hits": 0,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            },
        },
        "discord/user/999/memories": {
            "mem_global_dup": {
                "type": "project_fact",
                "text": "Fixture alpha uses LM Studio locally",
                "hits": 3,
                "created_at": "2026-06-06T12:00:00Z",
                "updated_at": "2026-06-06T12:00:00Z",
            },
            "mem_over_trigger": {
                "type": "user_preference",
                "text": "Synthetic long-form preference about concise debugging replies in bot channels",
                "hits": 12,
                "created_at": "2026-06-07T12:00:00Z",
                "updated_at": "2026-06-07T12:00:00Z",
            },
        },
    }


class MemoryPruningReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 7, tzinfo=timezone.utc)

    def _candidate_by_key(self, candidates: list[dict], key: str) -> dict:
        matches = [item for item in candidates if item["key"] == key]
        self.assertEqual(len(matches), 1, f"expected one candidate for {key}")
        return matches[0]

    def test_duplicate_detection_within_namespace(self):
        from tools.review_memory_pruning import scan_store

        candidates = scan_store(_synthetic_fixture_store(), now=self.now)
        dup_a = self._candidate_by_key(candidates, "mem_dup_a")
        dup_b = self._candidate_by_key(candidates, "mem_dup_b")

        self.assertIn("duplicate_namespace", dup_a["reasons"])
        self.assertIn("duplicate_namespace", dup_b["reasons"])

    def test_duplicate_detection_globally(self):
        from tools.review_memory_pruning import scan_store

        candidates = scan_store(_synthetic_fixture_store(), now=self.now)
        global_dup = self._candidate_by_key(candidates, "mem_global_dup")

        self.assertIn("duplicate_global", global_dup["reasons"])

    def test_suspicious_identity_terms(self):
        from tools.review_memory_pruning import scan_store

        candidate = self._candidate_by_key(
            scan_store(_synthetic_fixture_store(), now=self.now),
            "mem_identity",
        )

        self.assertIn("identity_contamination", candidate["reasons"])

    def test_suspicious_body_terms(self):
        from tools.review_memory_pruning import scan_store

        candidate = self._candidate_by_key(
            scan_store(_synthetic_fixture_store(), now=self.now),
            "mem_body",
        )

        self.assertIn("body_contamination", candidate["reasons"])

    def test_stale_relationship_claim(self):
        from tools.review_memory_pruning import scan_store

        candidate = self._candidate_by_key(
            scan_store(_synthetic_fixture_store(), now=self.now),
            "mem_scene",
        )

        self.assertIn("stale_relationship", candidate["reasons"])

    def test_high_hit_generic(self):
        from tools.review_memory_pruning import scan_store

        candidate = self._candidate_by_key(
            scan_store(_synthetic_fixture_store(), now=self.now),
            "mem_high_hit",
        )

        self.assertIn("high_hit_generic", candidate["reasons"])

    def test_high_hit_review_for_over_triggering(self):
        from tools.review_memory_pruning import scan_store

        candidate = self._candidate_by_key(
            scan_store(_synthetic_fixture_store(), now=self.now),
            "mem_over_trigger",
        )

        self.assertIn("high_hit_review", candidate["reasons"])
        self.assertNotIn("high_hit_generic", candidate["reasons"])

    def test_scene_joke_residue_in_durable_fact(self):
        from tools.review_memory_pruning import scan_store

        candidate = self._candidate_by_key(
            scan_store(_synthetic_fixture_store(), now=self.now),
            "mem_scene",
        )

        self.assertIn("scene_joke_residue", candidate["reasons"])

    def test_candidate_schema_is_stable(self):
        from tools.review_memory_pruning import scan_store

        candidate = self._candidate_by_key(
            scan_store(_synthetic_fixture_store(), now=self.now),
            "mem_identity",
        )

        self.assertEqual(
            set(candidate.keys()),
            {"namespace", "key", "type", "hits", "reasons", "text_preview"},
        )
        self.assertIsInstance(candidate["reasons"], list)

    def test_cli_json_output_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "memory_store.json"
            store = _synthetic_fixture_store()
            _write_store(store_path, store)
            before = hashlib.sha256(store_path.read_bytes()).hexdigest()

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "review_memory_pruning.py"),
                    str(store_path),
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            after = hashlib.sha256(store_path.read_bytes()).hexdigest()

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(before, after)

        payload = json.loads(completed.stdout)
        self.assertTrue(payload["review_only"])
        self.assertTrue(payload["no_changes_written"])
        self.assertGreater(payload["candidate_count"], 0)
        self.assertIn("counts_by_reason", payload)
        self.assertTrue(payload["candidates"])

        sample = payload["candidates"][0]
        self.assertEqual(
            set(sample.keys()),
            {"namespace", "key", "type", "hits", "reasons", "text_preview"},
        )

    def test_cli_text_output_includes_review_banner(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "memory_store.json"
            _write_store(store_path, _synthetic_fixture_store())

            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "review_memory_pruning.py"),
                    str(store_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("REVIEW ONLY: no changes were written", completed.stdout)
        self.assertIn("counts_by_reason:", completed.stdout)
        self.assertIn("candidate_lines:", completed.stdout)

    def test_cli_exits_nonzero_for_missing_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "review_memory_pruning.py"),
                    str(missing),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 1)
        self.assertIn("memory store not found", completed.stderr)


if __name__ == "__main__":
    unittest.main()
