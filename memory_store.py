"""
LangGraph-style JSON memory store for SOPPO.

This is a small compatibility seam for future migration: records are addressed by
(namespace tuple, key) and stored as flat JSON paths. The bot runtime uses this
store for channel summaries and structured long-term memory records.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

Namespace = tuple[str, ...]
MemoryValue = dict[str, Any]
MemoryData = dict[str, dict[str, MemoryValue]]


def _validate_namespace(namespace: Namespace) -> Namespace:
    if not isinstance(namespace, tuple) or not namespace:
        raise ValueError("namespace must be a non-empty tuple[str, ...]")

    clean_parts: list[str] = []
    for part in namespace:
        if not isinstance(part, str):
            raise ValueError("namespace parts must be strings")
        clean = part.strip()
        if not clean:
            raise ValueError("namespace parts must be non-empty")
        if "/" in clean:
            raise ValueError("namespace parts must not contain '/'")
        clean_parts.append(clean)
    return tuple(clean_parts)


def _validate_key(key: str) -> str:
    if not isinstance(key, str):
        raise ValueError("key must be a string")
    clean = key.strip()
    if not clean:
        raise ValueError("key must be non-empty")
    if "/" in clean:
        raise ValueError("key must not contain '/'")
    return clean


def _namespace_path(namespace: Namespace) -> str:
    return "/".join(_validate_namespace(namespace))


def _validate_value(value: MemoryValue) -> MemoryValue:
    if not isinstance(value, dict):
        raise TypeError("memory value must be a dict[str, Any]")
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise TypeError("memory value must be JSON-serializable") from exc
    # Return a JSON-normalized deep copy so callers cannot mutate stored state by reference.
    return json.loads(json.dumps(value))


class JsonMemoryStore:
    """Small in-memory facade over flat JSON-backed namespace records."""

    def __init__(self, data: MemoryData | None = None) -> None:
        self._data: MemoryData = {}
        if data:
            for namespace_path, records in data.items():
                if not isinstance(namespace_path, str) or not namespace_path.strip():
                    raise ValueError("stored namespace paths must be non-empty strings")
                if not isinstance(records, dict):
                    raise TypeError("stored namespace records must be dictionaries")
                normalized_records: dict[str, MemoryValue] = {}
                for key, value in records.items():
                    clean_key = _validate_key(key)
                    normalized_records[clean_key] = _validate_value(value)
                self._data[namespace_path.strip()] = normalized_records

    def get_memory(self, namespace: Namespace, key: str) -> MemoryValue | None:
        namespace_path = _namespace_path(namespace)
        clean_key = _validate_key(key)
        value = self._data.get(namespace_path, {}).get(clean_key)
        if value is None:
            return None
        return json.loads(json.dumps(value))

    def put_memory(self, namespace: Namespace, key: str, value: MemoryValue) -> None:
        namespace_path = _namespace_path(namespace)
        clean_key = _validate_key(key)
        clean_value = _validate_value(value)
        self._data.setdefault(namespace_path, {})[clean_key] = clean_value

    def search_namespace(self, namespace_prefix: Namespace) -> MemoryData:
        prefix_path = _namespace_path(namespace_prefix)
        matches: MemoryData = {}
        for namespace_path, records in self._data.items():
            if namespace_path == prefix_path or namespace_path.startswith(prefix_path + "/"):
                matches[namespace_path] = json.loads(json.dumps(records))
        return matches

    def to_json_data(self) -> MemoryData:
        return json.loads(json.dumps(self._data))


def load_memory_store(path: str | Path) -> JsonMemoryStore:
    store_path = Path(path)
    if not store_path.exists():
        return JsonMemoryStore()
    with store_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise TypeError("memory store JSON root must be an object")
    return JsonMemoryStore(raw)


def save_memory_store(path: str | Path, store: JsonMemoryStore) -> None:
    store_path = Path(path)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    with store_path.open("w", encoding="utf-8") as f:
        json.dump(store.to_json_data(), f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
