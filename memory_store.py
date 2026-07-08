"""
LangGraph-style JSON memory store for SOPPO.

This is a small compatibility seam for future migration: records are addressed by
(namespace tuple, key) and stored as flat JSON paths. The bot runtime uses this
store for channel summaries and structured long-term memory records.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

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


def _normalize_memory_data(raw: object) -> MemoryData:
    if not isinstance(raw, dict):
        raise TypeError("memory store JSON root must be an object")
    normalized: MemoryData = {}
    for namespace_path, records in raw.items():
        if not isinstance(namespace_path, str) or not namespace_path.strip():
            raise ValueError("stored namespace paths must be non-empty strings")
        if not isinstance(records, dict):
            raise TypeError("stored namespace records must be dictionaries")
        clean_namespace = namespace_path.strip()
        normalized_records: dict[str, MemoryValue] = {}
        for key, value in records.items():
            clean_key = _validate_key(key)
            normalized_records[clean_key] = _validate_value(value)
        normalized[clean_namespace] = normalized_records
    return normalized


def _deep_copy_memory_data(data: MemoryData) -> MemoryData:
    return json.loads(json.dumps(data))


def merge_memory_data_for_save(disk: MemoryData, store: MemoryData) -> MemoryData:
    """Merge in-memory store onto disk; store wins per key, disk-only keys preserved."""
    merged = _deep_copy_memory_data(disk)
    for namespace_path, records in store.items():
        if not isinstance(records, dict):
            continue
        namespace_records = merged.setdefault(namespace_path, {})
        for key, value in records.items():
            if isinstance(value, dict):
                namespace_records[key] = _validate_value(value)
    return merged


def merge_memory_data_for_refresh(store: MemoryData, disk: MemoryData) -> MemoryData:
    """Merge disk into store; store wins per key, disk-only keys are added."""
    merged = _deep_copy_memory_data(store)
    for namespace_path, records in disk.items():
        if not isinstance(records, dict):
            continue
        namespace_records = merged.setdefault(namespace_path, {})
        for key, value in records.items():
            if key not in namespace_records and isinstance(value, dict):
                namespace_records[key] = _validate_value(value)
    return merged


def _is_memory_only_path(path: str | Path) -> bool:
    return str(path) == ":memory:"


def _lock_path(store_path: Path) -> Path:
    return store_path.with_name(store_path.name + ".lock")


@contextmanager
def memory_store_file_lock(store_path: str | Path) -> Iterator[None]:
    """Cross-process exclusive lock for memory_store.json read/modify/write."""
    path = Path(store_path)
    lock_path = _lock_path(path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _load_raw_memory_data(path: Path) -> MemoryData:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    return _normalize_memory_data(raw)


def _atomic_write_json(path: Path, data: MemoryData) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


class JsonMemoryStore:
    """Small in-memory facade over flat JSON-backed namespace records."""

    def __init__(self, data: MemoryData | None = None) -> None:
        self._data: MemoryData = {}
        if data:
            self.replace_data(data)

    def replace_data(self, data: MemoryData) -> None:
        self._data = _normalize_memory_data(data)

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
    if _is_memory_only_path(path):
        return JsonMemoryStore()
    store_path = Path(path)
    with memory_store_file_lock(store_path):
        return JsonMemoryStore(_load_raw_memory_data(store_path))


def refresh_memory_store_from_disk(store: JsonMemoryStore, path: str | Path) -> None:
    """Pick up externally written namespaces/keys without overwriting in-memory edits."""
    if _is_memory_only_path(path):
        return
    store_path = Path(path)
    with memory_store_file_lock(store_path):
        disk = _load_raw_memory_data(store_path)
        merged = merge_memory_data_for_refresh(store.to_json_data(), disk)
        store.replace_data(merged)


def save_memory_store(path: str | Path, store: JsonMemoryStore) -> None:
    if _is_memory_only_path(path):
        return
    store_path = Path(path)
    with memory_store_file_lock(store_path):
        disk = _load_raw_memory_data(store_path)
        merged = merge_memory_data_for_save(disk, store.to_json_data())
        _atomic_write_json(store_path, merged)
        store.replace_data(merged)
