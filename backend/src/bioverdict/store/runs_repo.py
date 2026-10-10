"""Runs, their progress events and the claims they produced (SQLite).

Each function commits on its own: a run is written to by a few small steps, not by one long
transaction.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime

from bioverdict.store.migrations import SCHEMA_VERSION
from bioverdict.store.models import Claim, ClaimEvidenceLink, ResolverOutput, VerdictResult

RUNNING, DONE, FAILED = "running", "done", "failed"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    input: dict
    as_of: date
    status: str
    verdict: str | None
    created_at: datetime
    finished_at: datetime | None
    resolver: ResolverOutput | None
    result: VerdictResult | None


@dataclass(frozen=True)
class RunEvent:
    seq: int
    step: str
    status: str
    detail: str
    created_at: datetime


def _now() -> datetime:
    return datetime.now(UTC)


# --- runs ---------------------------------------------------------------------


def create_run(conn: sqlite3.Connection, run_id: str, input_data: dict, as_of: date) -> None:
    with conn:
        conn.execute(
            "INSERT INTO runs (run_id, input_json, as_of, status, created_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                run_id,
                json.dumps(input_data, ensure_ascii=False),
                as_of.isoformat(),
                RUNNING,
                _now().isoformat(),
                SCHEMA_VERSION,
            ),
        )


def save_resolver(conn: sqlite3.Connection, run_id: str, resolver: ResolverOutput) -> None:
    with conn:
        conn.execute(
            "UPDATE runs SET resolver_json = ? WHERE run_id = ?",
            (resolver.model_dump_json(), run_id),
        )


def finish_run(
    conn: sqlite3.Connection, run_id: str, status: str, result: VerdictResult | None = None
) -> None:
    with conn:
        conn.execute(
            "UPDATE runs SET status = ?, verdict = ?, result_json = ?, finished_at = ? "
            "WHERE run_id = ?",
            (
                status,
                result.verdict.value if result else None,
                result.model_dump_json() if result else None,
                _now().isoformat(),
                run_id,
            ),
        )


def _to_record(row: sqlite3.Row) -> RunRecord:
    finished = row["finished_at"]
    resolver, result = row["resolver_json"], row["result_json"]
    return RunRecord(
        run_id=row["run_id"],
        input=json.loads(row["input_json"]),
        as_of=date.fromisoformat(row["as_of"]),
        status=row["status"],
        verdict=row["verdict"],
        created_at=datetime.fromisoformat(row["created_at"]),
        finished_at=datetime.fromisoformat(finished) if finished else None,
        resolver=ResolverOutput.model_validate_json(resolver) if resolver else None,
        result=VerdictResult.model_validate_json(result) if result else None,
    )


def get_run(conn: sqlite3.Connection, run_id: str) -> RunRecord | None:
    row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    return None if row is None else _to_record(row)


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[RunRecord]:
    rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))
    return [_to_record(row) for row in rows]


# --- progress events ------------------------------------------------------------


def add_event(
    conn: sqlite3.Connection, run_id: str, step: str, status: str, detail: str = ""
) -> RunEvent:
    with conn:
        last = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) FROM run_events WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        created = _now()
        conn.execute(
            "INSERT INTO run_events (run_id, seq, step, status, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, last + 1, step, status, detail, created.isoformat()),
        )
    return RunEvent(last + 1, step, status, detail, created)


def load_events(conn: sqlite3.Connection, run_id: str, after_seq: int = 0) -> list[RunEvent]:
    rows = conn.execute(
        "SELECT seq, step, status, detail, created_at FROM run_events "
        "WHERE run_id = ? AND seq > ? ORDER BY seq",
        (run_id, after_seq),
    )
    return [
        RunEvent(
            r["seq"], r["step"], r["status"], r["detail"], datetime.fromisoformat(r["created_at"])
        )
        for r in rows
    ]


# --- claims ---------------------------------------------------------------------


def save_claims(
    conn: sqlite3.Connection,
    run_id: str,
    claims: list[Claim],
    links: list[ClaimEvidenceLink],
    version: int,
) -> None:
    claim_rows = [
        {
            "run_id": run_id,
            "id": claim.id,
            "section": claim.section.value,
            "claim_type": claim.claim_type.value,
            "text": claim.text,
            "basis": claim.basis.value,
            "status": claim.status.value,
            "confidence": claim.confidence,
            "confidence_parts_json": (
                claim.confidence_parts.model_dump_json() if claim.confidence_parts else None
            ),
            "flags_json": json.dumps([flag.value for flag in claim.flags]),
            "depends_on_json": json.dumps(claim.depends_on),
            "diligence_type": claim.diligence_type.value if claim.diligence_type else None,
            "chain_link": claim.chain_link.value if claim.chain_link else None,
            "gate_signals_json": json.dumps([gate.value for gate in claim.gate_signals]),
            "critical": int(claim.critical),
            "implication": claim.implication.value,
            "version": version,
        }
        for claim in claims
    ]
    with conn:
        conn.executemany(
            "INSERT INTO claims (run_id, id, section, claim_type, text, basis, status, confidence, "
            "confidence_parts_json, flags_json, depends_on_json, diligence_type, chain_link, "
            "gate_signals_json, critical, implication, version) VALUES (:run_id, :id, :section, :claim_type, "
            ":text, :basis, :status, :confidence, :confidence_parts_json, :flags_json, "
            ":depends_on_json, :diligence_type, :chain_link, :gate_signals_json, :critical, "
            ":implication, :version)",
            claim_rows,
        )
        conn.executemany(
            "INSERT INTO claim_evidence (run_id, claim_id, evidence_id, direction, quote) "
            "VALUES (?, ?, ?, ?, ?)",
            [(run_id, l.claim_id, l.evidence_id, l.direction.value, l.quote) for l in links],
        )


def load_claims(
    conn: sqlite3.Connection, run_id: str
) -> tuple[list[Claim], list[ClaimEvidenceLink]]:
    claims = []
    for row in conn.execute("SELECT * FROM claims WHERE run_id = ? ORDER BY id", (run_id,)):
        parts = row["confidence_parts_json"]
        claims.append(
            Claim.model_validate(
                {
                    "id": row["id"],
                    "run_id": run_id,
                    "section": row["section"],
                    "text": row["text"],
                    "claim_type": row["claim_type"],
                    "basis": row["basis"],
                    "status": row["status"],
                    "confidence": row["confidence"],
                    "confidence_parts": json.loads(parts) if parts else None,
                    "flags": json.loads(row["flags_json"]),
                    "depends_on": json.loads(row["depends_on_json"]),
                    "diligence_type": row["diligence_type"],
                    "chain_link": row["chain_link"],
                    "gate_signals": json.loads(row["gate_signals_json"]),
                    "critical": bool(row["critical"]),
                    # Runs stored before the column existed have no label: neutral.
                    "implication": row["implication"] or "neutral",
                }
            )
        )
    links = [
        ClaimEvidenceLink.model_validate(dict(row))
        for row in conn.execute(
            "SELECT claim_id, evidence_id, direction, quote FROM claim_evidence "
            "WHERE run_id = ? ORDER BY claim_id, evidence_id",
            (run_id,),
        )
    ]
    return claims, links
