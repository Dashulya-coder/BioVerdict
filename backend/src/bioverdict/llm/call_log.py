"""One row per LLM call, in the `llm_calls` table (docs/data-model.md). Feeds the trace panel."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from bioverdict.store.db import connect


@dataclass(frozen=True)
class CallRecord:
    run_id: str | None
    step: str
    provider: str
    model: str
    effort: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    attempts: int
    cache_hit: bool
    failover_from: str | None = None
    error: str | None = None


class CallLog(Protocol):
    def record(self, entry: CallRecord) -> None: ...


@dataclass
class MemoryCallLog:
    entries: list[CallRecord] = field(default_factory=list)

    def record(self, entry: CallRecord) -> None:
        self.entries.append(entry)


class SqliteCallLog:
    """Writes to `llm_calls`. A connection per write keeps it safe for parallel agents (WAL)."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = db_path
        self._lock = threading.Lock()

    def record(self, entry: CallRecord) -> None:
        with self._lock:
            conn = connect(self._path)
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO llm_calls (run_id, step, provider, model, effort, "
                        "input_tokens, output_tokens, cost_usd, latency_ms, attempts, cache_hit, "
                        "failover_from, error, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            entry.run_id,
                            entry.step,
                            entry.provider,
                            entry.model,
                            entry.effort,
                            entry.input_tokens,
                            entry.output_tokens,
                            entry.cost_usd,
                            entry.latency_ms,
                            entry.attempts,
                            int(entry.cache_hit),
                            entry.failover_from,
                            entry.error,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
            finally:
                conn.close()
