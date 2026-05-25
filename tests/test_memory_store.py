import json
import tempfile
import unittest
from pathlib import Path


class JsonMemoryStoreTests(unittest.TestCase):
    def test_put_and_get_round_trip_document_by_namespace_and_key(self):
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        namespace = ("discord", "guild", "123", "channel", "456", "summary")
        value = {"text": "SOPPO remembers the plan.", "updated_at": "2026-05-25T15:30:00Z"}

        store.put_memory(namespace, "current", value)

        self.assertEqual(store.get_memory(namespace, "current"), value)

    def test_missing_key_returns_none(self):
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()

        self.assertIsNone(store.get_memory(("discord", "guild", "123"), "missing"))

    def test_namespace_prefix_search_returns_matching_records_only(self):
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()
        store.put_memory(("discord", "guild", "123", "channel", "1", "summary"), "current", {"text": "one"})
        store.put_memory(("discord", "guild", "123", "channel", "2", "summary"), "current", {"text": "two"})
        store.put_memory(("discord", "guild", "999", "channel", "3", "summary"), "current", {"text": "other"})

        results = store.search_namespace(("discord", "guild", "123"))

        self.assertEqual(set(results.keys()), {
            "discord/guild/123/channel/1/summary",
            "discord/guild/123/channel/2/summary",
        })
        self.assertEqual(results["discord/guild/123/channel/1/summary"]["current"], {"text": "one"})

    def test_json_round_trip_uses_flat_namespace_key_shape(self):
        from memory_store import JsonMemoryStore, load_memory_store, save_memory_store

        namespace = ("discord", "guild", "123", "channel", "456", "summary")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory_store.json"
            store = JsonMemoryStore()
            store.put_memory(namespace, "current", {"text": "persist me", "updated_at": "now"})

            save_memory_store(path, store)
            raw = json.loads(path.read_text(encoding="utf-8"))
            loaded = load_memory_store(path)

        self.assertEqual(raw, {
            "discord/guild/123/channel/456/summary": {
                "current": {"text": "persist me", "updated_at": "now"}
            }
        })
        self.assertEqual(loaded.get_memory(namespace, "current"), {"text": "persist me", "updated_at": "now"})

    def test_missing_json_file_loads_empty_store(self):
        from memory_store import load_memory_store

        with tempfile.TemporaryDirectory() as tmp:
            store = load_memory_store(Path(tmp) / "missing.json")

        self.assertEqual(store.search_namespace(("discord",)), {})

    def test_invalid_namespace_and_key_handling(self):
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()

        invalid_namespaces = [(), ("discord/guild",), ("",), ("discord", "  ")]
        for namespace in invalid_namespaces:
            with self.subTest(namespace=namespace):
                with self.assertRaises(ValueError):
                    store.put_memory(namespace, "current", {"text": "bad"})

        invalid_keys = ["", "  ", "current/key"]
        for key in invalid_keys:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    store.put_memory(("discord",), key, {"text": "bad"})

    def test_value_must_be_json_serializable_dict(self):
        from memory_store import JsonMemoryStore

        store = JsonMemoryStore()

        with self.assertRaises(TypeError):
            store.put_memory(("discord",), "current", ["not", "a", "dict"])  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            store.put_memory(("discord",), "current", {"bad": object()})


if __name__ == "__main__":
    unittest.main()
