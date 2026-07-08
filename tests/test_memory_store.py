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

    def test_memory_only_path_does_not_create_literal_file(self):
        from memory_store import JsonMemoryStore, load_memory_store, save_memory_store

        path = Path(":memory:")
        lock_path = Path(":memory:.lock")
        path.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)
        store = JsonMemoryStore()
        store.put_memory(("discord",), "current", {"text": "ephemeral"})

        save_memory_store(path, store)
        loaded = load_memory_store(path)

        self.assertFalse(path.exists())
        self.assertFalse(lock_path.exists())
        self.assertEqual(loaded.search_namespace(("discord",)), {})

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

    def test_merge_for_save_preserves_externally_added_namespace(self):
        import json
        from memory import PersistentChannelSummaryMemory
        from memory_extractor import global_memories_namespace
        from memory_store import load_memory_store

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory_store.json"
            path.write_text(
                json.dumps(
                    {
                        "discord/guild/123/channel/456/summary": {
                            "current": {"text": "- old summary", "mode": "neutral"}
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            memory = PersistentChannelSummaryMemory(path)
            external_namespace = "/".join(global_memories_namespace())
            external_record = {
                "mem_external123": {
                    "type": "character_note",
                    "text": "SOPPO likes debugging with SKK",
                    "importance": 0.7,
                    "source": "manual_review",
                    "created_at": "2026-07-07T00:00:00Z",
                    "updated_at": "2026-07-07T00:00:00Z",
                    "last_seen_at": "2026-07-07T00:00:00Z",
                    "hits": 1,
                }
            }
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            on_disk[external_namespace] = external_record
            path.write_text(json.dumps(on_disk, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            memory.update_summary_metadata(
                guild_id=123,
                channel_id=456,
                messages_since_regen=3,
                last_regen_status="waiting_threshold",
            )

            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(external_namespace, saved)
            self.assertEqual(saved[external_namespace]["mem_external123"]["text"], "SOPPO likes debugging with SKK")
            summary = saved["discord/guild/123/channel/456/summary"]["current"]
            self.assertEqual(summary["messages_since_regen"], 3)
            self.assertEqual(summary["last_regen_status"], "waiting_threshold")

            reloaded = load_memory_store(path)
            self.assertIsNotNone(reloaded.get_memory(global_memories_namespace(), "mem_external123"))

    def test_refresh_from_disk_picks_up_external_write(self):
        import json
        from memory import PersistentChannelSummaryMemory
        from memory_extractor import global_memories_namespace

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory_store.json"
            path.write_text(
                json.dumps(
                    {
                        "discord/guild/123/channel/456/summary": {
                            "current": {"text": "- summary", "mode": "neutral"}
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            memory = PersistentChannelSummaryMemory(path)
            external_namespace = "/".join(global_memories_namespace())
            on_disk = json.loads(path.read_text(encoding="utf-8"))
            on_disk[external_namespace] = {
                "mem_refresh001": {
                    "type": "project_fact",
                    "text": "We are using merge-safe memory writes",
                    "importance": 0.8,
                    "source": "manual_review",
                    "created_at": "2026-07-07T00:00:00Z",
                    "updated_at": "2026-07-07T00:00:00Z",
                    "last_seen_at": "2026-07-07T00:00:00Z",
                    "hits": 1,
                }
            }
            path.write_text(json.dumps(on_disk, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            memory.reload_from_disk()

            record = memory.store.get_memory(global_memories_namespace(), "mem_refresh001")
            self.assertIsNotNone(record)
            assert record is not None
            self.assertEqual(record["type"], "project_fact")


if __name__ == "__main__":
    unittest.main()
