"""Response cache keyed by a hash of (model, parameters, schema, prompt).

Entries never expire, so a recorded run replays identically (demo, regression tests). Files are
written atomically; the directory is CACHE_DIR/llm.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

from bioverdict.llm.types import ProviderRequest


def cache_key(model_ref: str, request: ProviderRequest) -> str:
    payload = {
        "model": model_ref,
        "effort": request.effort,
        "temperature": request.temperature,
        "max_tokens": request.max_tokens,
        "system": request.system,
        "schema": request.schema.model_json_schema(),
        "prompt": request.prompt,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LLMCache(Protocol):
    def get(self, key: str) -> dict | None: ...

    def put(self, key: str, value: dict) -> None: ...


class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        return self._data.get(key)

    def put(self, key: str, value: dict) -> None:
        self._data[key] = value


class DiskCache:
    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict | None:
        path = self._dir / f"{key}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError, json.JSONDecodeError:
            return None  # a torn or missing file is just a miss

    def put(self, key: str, value: dict) -> None:
        fd, tmp = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False)
        os.replace(tmp, self._dir / f"{key}.json")
