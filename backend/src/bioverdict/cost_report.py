"""What runs cost: a table of the `llm_calls` log, for `bioverdict cost`.

The figures are the ones the client computed from token counts and its price table
(`docs/cost.md`); compare them with the gateway portal to check the prices.
"""

from __future__ import annotations

import sqlite3


def _row(cells: list[str], widths: list[int]) -> str:
    return "  ".join(
        c.ljust(w) if i == 0 else c.rjust(w)
        for i, (c, w) in enumerate(zip(cells, widths, strict=True))
    ).rstrip()


def _table(header: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
    return "\n".join([_row(header, widths), *(_row(r, widths) for r in rows)]) + "\n"


def cost_of_runs(conn: sqlite3.Connection, limit: int = 10) -> str:
    """The latest runs: calls, cache hits, tokens, cost and the slowest call."""
    found = conn.execute(
        "SELECT run_id, COUNT(*), SUM(cache_hit), SUM(input_tokens), SUM(output_tokens), "
        "SUM(cost_usd), MAX(latency_ms), SUM(error IS NOT NULL) FROM llm_calls "
        "GROUP BY run_id ORDER BY MIN(id) DESC LIMIT ?",
        (limit,),
    ).fetchall()
    if not found:
        return "No model calls are logged yet.\n"
    rows = [
        [
            r[0],
            str(r[1]),
            str(r[2] or 0),
            f"{r[3] or 0:,}",
            f"{r[4] or 0:,}",
            f"${r[5] or 0:.4f}",
            f"{(r[6] or 0) / 1000:.0f} s",
            str(r[7] or 0),
        ]
        for r in found
    ]
    total = sum(r[5] or 0 for r in found)
    header = ["run", "calls", "cached", "in tokens", "out tokens", "cost", "slowest", "errors"]
    return _table(header, rows) + f"Total of these runs: ${total:.4f}\n"


def cost_of_run(conn: sqlite3.Connection, run_id: str) -> str:
    """One run, step by step (calls answered from the cache cost nothing)."""
    found = conn.execute(
        "SELECT step, model, COUNT(*), SUM(cache_hit), SUM(input_tokens), SUM(output_tokens), "
        "SUM(cost_usd), MAX(latency_ms) FROM llm_calls WHERE run_id = ? "
        "GROUP BY step, model ORDER BY MIN(id)",
        (run_id,),
    ).fetchall()
    if not found:
        return f"No model calls are logged for {run_id}.\n"
    rows = [
        [
            f"{r[0]} ({r[1]})",
            str(r[2]),
            str(r[3] or 0),
            f"{r[4] or 0:,}",
            f"{r[5] or 0:,}",
            f"${r[6] or 0:.4f}",
            f"{(r[7] or 0) / 1000:.0f} s",
        ]
        for r in found
    ]
    total = sum(r[6] or 0 for r in found)
    header = ["step (model)", "calls", "cached", "in tokens", "out tokens", "cost", "slowest"]
    return _table(header, rows) + f"Total: ${total:.4f}\n"
