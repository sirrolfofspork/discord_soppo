import json
import tempfile
import unittest
from pathlib import Path

from lore import build_lore_context_block, find_relevant_lore, load_lore_store


class LoreRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.store = {
            "g11": {
                "aliases": ["g11", "g 11"],
                "summary": "Sleepy 404 Squad T-Doll.",
                "soppo_take": "SOPPO finds her laziness funny but useful.",
            },
            "m4a1": {
                "aliases": ["m4a1", "m4"],
                "summary": "AR Team leader.",
                "soppo_take": "SOPPO is loyal to her.",
            },
            "ar_team": {
                "aliases": ["ar team", "ar-team"],
                "summary": "Core Griffin AR squad.",
                "soppo_take": "SOPPO treats them like family.",
            },
            "ro635": {
                "aliases": ["ro635", "ro 635", "ro"],
                "summary": "AR Team member.",
                "soppo_take": "SOPPO respects her dependable side.",
            },
        }

    def test_alias_matching_is_case_insensitive_and_whole_term(self):
        matches = find_relevant_lore("Tell me about G11 and M4A1.", self.store)
        self.assertEqual([m["id"] for m in matches], ["g11", "m4a1"])

        non_matches = find_relevant_lore("The programming language m4a1x is not a doll.", self.store)
        self.assertEqual(non_matches, [])

    def test_non_matching_message_returns_empty_list(self):
        self.assertEqual(find_relevant_lore("Nothing about the dolls here.", self.store), [])
        self.assertEqual(find_relevant_lore("", self.store), [])

    def test_lore_block_formatting_is_compact_system_context(self):
        matches = find_relevant_lore("RO635, report in.", self.store)
        block = build_lore_context_block(matches)

        self.assertIn("[Relevant lore context]", block)
        self.assertIn("- ro635", block)
        self.assertIn("Summary: AR Team member.", block)
        self.assertIn("SOPPO angle: SOPPO respects her dependable side.", block)
        self.assertIn("Use this naturally if relevant.", block)

    def test_default_match_limit_is_three(self):
        matches = find_relevant_lore("G11 M4A1 AR Team RO635", self.store)
        self.assertEqual([m["id"] for m in matches], ["g11", "m4a1", "ar_team"])

    def test_load_lore_store_reads_json_dict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "lore_store.json"
            path.write_text(json.dumps(self.store), encoding="utf-8")

            loaded = load_lore_store(path)

        self.assertEqual(loaded["g11"]["aliases"], ["g11", "g 11"])


if __name__ == "__main__":
    unittest.main()
