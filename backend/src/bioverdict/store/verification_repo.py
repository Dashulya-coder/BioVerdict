"""The `verification_log` table: every check a claim went through, passed or not."""

from __future__ import annotations

import sqlite3

from bioverdict.store.models import VerificationCheck


def save_checks(conn: sqlite3.Connection, run_id: str, checks: list[VerificationCheck]) -> None:
    with conn:
        conn.executemany(
            "INSERT INTO verification_log (run_id, claim_id, check_name, passed, detail) "
            "VALUES (?, ?, ?, ?, ?)",
            [(run_id, c.claim_id, c.check_name, int(c.passed), c.detail) for c in checks],
        )


def load_checks(conn: sqlite3.Connection, run_id: str) -> list[VerificationCheck]:
    rows = conn.execute(
        "SELECT claim_id, check_name, passed, detail FROM verification_log "
        "WHERE run_id = ? ORDER BY id",
        (run_id,),
    )
    return [
        VerificationCheck(
            claim_id=row["claim_id"],
            check_name=row["check_name"],
            passed=bool(row["passed"]),
            detail=row["detail"],
        )
        for row in rows
    ]
