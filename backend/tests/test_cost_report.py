import sqlite3
from pathlib import Path

from bioverdict.cost_report import cost_of_run, cost_of_runs
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    for run, step, cost, hit, err in [
        ("R-1", "extraction", 0.01, 0, None),
        ("R-1", "reasoning.clinical", 0.04, 0, None),
        ("R-1", "reasoning.clinical", 0.0, 1, None),
        ("R-2", "reasoning.clinical", 0.02, 0, "boom"),
    ]:
        conn.execute(
            "INSERT INTO llm_calls (run_id, step, provider, model, effort, input_tokens, "
            "output_tokens, cost_usd, latency_ms, attempts, cache_hit, failover_from, error, "
            "created_at) VALUES (?, ?, 'openai', 'm', 'low', 100, 50, ?, 2000, 1, ?, NULL, ?, 'now')",
            (run, step, cost, hit, err),
        )
    conn.commit()
    return conn


def test_the_latest_runs_are_listed_with_their_total(tmp_path: Path) -> None:
    text = cost_of_runs(_db(tmp_path))
    assert (
        "R-1" in text
        and "R-2" in text
        and "$0.0500" in text
        and "Total of these runs: $0.0700" in text
    )


def test_one_run_is_listed_step_by_step(tmp_path: Path) -> None:
    text = cost_of_run(_db(tmp_path), "R-1")
    assert "reasoning.clinical (m)" in text and "Total: $0.0500" in text
    assert "No model calls" in cost_of_run(_db(tmp_path), "R-nope")


def test_an_empty_log_says_so(tmp_path: Path) -> None:
    conn = connect(tmp_path / "e.db")
    migrate(conn)
    assert "No model calls" in cost_of_runs(conn)
