import json
import tempfile
import unittest
from pathlib import Path


class ImportMemoryCandidatesTests(unittest.TestCase):
    def _write_jsonl(self, path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def test_converts_curated_rows_to_pending_queue_items(self):
        from tools.import_memory_candidates import run_import

        curated = [
            {
                "id": "mem_0001",
                "category": "identity",
                "reality": "factual",
                "sensitivity": "low",
                "importance_scores": {"overall": 5, "durability": 5},
                "source_count": 2,
                "evidence_count": 1,
                "memory_text": "My chosen personal name is Sash.",
                "evidence": [{"source_file": "diary.docx", "location": "paragraph[1]"}],
            },
            {
                "id": "mem_0002",
                "category": "project",
                "reality": "factual",
                "sensitivity": "low",
                "importance_scores": {"overall": 4},
                "source_count": 1,
                "evidence_count": 1,
                "memory_text": "lore_store.json anchors reboot continuity.",
                "evidence": [{"source_file": "notes.txt", "location": "line 10"}],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "curated.jsonl"
            output_path = Path(tmp) / "queue.jsonl"
            self._write_jsonl(input_path, curated)

            items = run_import(
                input_path,
                output_path,
                namespace="soppo/global/memories",
                scope="global",
                user_id=None,
                type_override=None,
                confidence_override=None,
                force=False,
                dry_run=False,
            )

            self.assertEqual(len(items), 2)
            self.assertTrue(output_path.exists())
            with output_path.open("r", encoding="utf-8") as fh:
                written = [json.loads(line) for line in fh if line.strip()]
            self.assertEqual(len(written), 2)

            first = written[0]
            self.assertEqual(first["status"], "pending")
            self.assertEqual(first["namespace"], "soppo/global/memories")
            self.assertEqual(first["candidate"]["type"], "character_note")
            self.assertEqual(first["candidate"]["scope"], "global")
            self.assertEqual(first["candidate"]["text"], "My chosen personal name is Sash.")
            self.assertEqual(first["candidate"]["confidence"], 0.95)
            self.assertEqual(first["source"]["source_id"], "mem_0001")
            self.assertEqual(first["source"]["category"], "identity")
            self.assertEqual(first["source"]["evidence_count"], 1)
            self.assertEqual(len(first["source"]["evidence"]), 1)

            second = written[1]
            self.assertEqual(second["candidate"]["type"], "project_fact")
            self.assertEqual(second["candidate"]["confidence"], 0.8)

    def test_refuses_overwrite_without_force(self):
        from tools.import_memory_candidates import run_import

        row = {
            "id": "mem_x",
            "category": "identity",
            "memory_text": "Sash is SOPPO.",
            "importance_scores": {"overall": 5},
        }

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "curated.jsonl"
            output_path = Path(tmp) / "queue.jsonl"
            self._write_jsonl(input_path, [row])
            output_path.write_text('{"existing": true}\n', encoding="utf-8")

            with self.assertRaises(FileExistsError):
                run_import(
                    input_path,
                    output_path,
                    namespace="soppo/global/memories",
                    scope="global",
                    user_id=None,
                    type_override=None,
                    confidence_override=None,
                    force=False,
                    dry_run=False,
                )

    def test_malformed_jsonl_fails_before_output(self):
        from tools.import_memory_candidates import run_import

        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "bad.jsonl"
            output_path = Path(tmp) / "queue.jsonl"
            input_path.write_text('{"id":"mem_1","memory_text":"ok"}\n{broken json\n', encoding="utf-8")

            with self.assertRaises(ValueError):
                run_import(
                    input_path,
                    output_path,
                    namespace="soppo/global/memories",
                    scope="global",
                    user_id=None,
                    type_override=None,
                    confidence_override=None,
                    force=False,
                    dry_run=False,
                )
            self.assertFalse(output_path.exists())

    def test_duplicate_source_ids_with_different_text_get_distinct_item_ids(self):
        from tools.import_memory_candidates import convert_rows

        rows = [
            {"id": "mem_dup", "category": "relationship", "memory_text": "First Quinn note."},
            {"id": "mem_dup", "category": "relationship", "memory_text": "Second Quinn note."},
        ]
        items = convert_rows(
            rows,
            namespace="soppo/global/memories",
            scope="global",
            user_id=None,
            type_override=None,
            confidence_override=None,
        )
        ids = [item["id"] for item in items]
        self.assertEqual(len(set(ids)), 2)
        self.assertTrue(all(item_id.startswith("import_mem_dup_") for item_id in ids))

    def test_category_mapping(self):
        from tools.import_memory_candidates import map_category_to_type

        self.assertEqual(map_category_to_type("identity", user_id=None, type_override=None), "character_note")
        self.assertEqual(map_category_to_type("relationship", user_id=None, type_override=None), "relationship_note")
        self.assertEqual(map_category_to_type("preference", user_id=111, type_override=None), "user_preference")
        self.assertEqual(map_category_to_type("preference", user_id=None, type_override=None), "character_note")
        self.assertEqual(map_category_to_type("lore", user_id=None, type_override=None), "project_fact")
        self.assertEqual(map_category_to_type("boundary", user_id=None, type_override=None), "character_note")
        self.assertEqual(map_category_to_type("unknown", user_id=None, type_override=None), "character_note")
        self.assertEqual(map_category_to_type("identity", user_id=None, type_override="project_fact"), "project_fact")

    def test_blank_memory_text_raises(self):
        from tools.import_memory_candidates import build_queue_item

        with self.assertRaises(ValueError):
            build_queue_item(
                {"id": "mem_blank", "category": "identity", "memory_text": "   "},
                namespace="soppo/global/memories",
                scope="global",
                user_id=None,
                type_override=None,
                confidence_override=None,
                created_at="2026-07-07T00:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
