"""The HTTP API (docs/architecture.md, section 12).

Runs are answered from fixtures by default and from the live pipeline with `USE_FIXTURES=0`. The
routes and the response shapes are the same for both: the UI does not tell them apart.

Every route opens its own SQLite connection inside its body and closes it again, so no connection
ever crosses a thread.
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from bioverdict import settings
from bioverdict.api import report
from bioverdict.api.diff import build_diff
from bioverdict.api.schemas import (
    AddEvidenceRequest,
    ClaimView,
    DiffResponse,
    EvidenceView,
    FinancialsResponse,
    MarketResponse,
    ReportResponse,
    RunCreated,
    RunRequest,
    RunSummary,
    TraceResponse,
)
from bioverdict.llm.errors import ConfigError
from bioverdict.pipeline.fixture_run import fixture_names, run_fixture
from bioverdict.pipeline.live_llm import live_llm, require_configured
from bioverdict.pipeline.live_run import LiveRunner, LLMFactory, describe_request, run_live
from bioverdict.pipeline.recompute import (
    PARENT,
    RecomputeError,
    analyst_evidence,
    finish_recompute,
    prepare_recompute,
)
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.models import ResolverOutput
from bioverdict.store.runs_repo import DONE, FAILED, create_run, get_run, list_runs, load_events

POLL_SECONDS = 0.2
KEEPALIVE_SECONDS = 15


def new_run_id() -> str:
    return f"R-{datetime.now(UTC):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def create_app(
    db_path: Path | None = None,
    fixtures: Path | None = None,
    live: LiveRunner | None = None,
    llm: LLMFactory | None = None,
) -> FastAPI:
    """`live` replaces the real live pipeline (sources and model) and `llm` the model that
    reasons over added evidence; tests pass stand-ins."""
    app = FastAPI(title="BioVerdict API", version="0.1.0")
    app.state.db_path = db_path
    app.state.fixtures = fixtures

    origins = os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def database(request: Request):
        return closing(settings.open_database(request.app.state.db_path))

    def fixtures_dir(request: Request) -> Path:
        return request.app.state.fixtures or settings.fixtures_dir()

    @app.get("/health")
    def health() -> dict[str, str]:
        """`mode` tells a client whether runs are answered from fixtures or are live."""
        return {"status": "ok", "mode": "fixtures" if settings.use_fixtures() else "live"}

    @app.post("/runs", status_code=202)
    def start_run(body: RunRequest, tasks: BackgroundTasks, request: Request) -> RunCreated:
        db = request.app.state.db_path
        fixture_mode = settings.use_fixtures()
        asset = (body.asset or "").strip()
        text = describe_request(body.asset, body.indication, body.mechanism)
        if fixture_mode:
            known = fixture_names(fixtures_dir(request))
            if asset.casefold() not in known:
                detail = f"fixture mode knows only these assets: {', '.join(known) or 'none'}"
                raise HTTPException(422, detail)
        else:
            if not text:
                raise HTTPException(422, "give an asset, or an indication with a mechanism")
            if live is None:
                try:
                    require_configured()
                except ConfigError as exc:
                    raise HTTPException(503, str(exc)) from exc

        run_id, as_of = new_run_id(), body.as_of or settings.today()
        with database(request) as conn:
            create_run(conn, run_id, body.model_dump(mode="json"), as_of)
        if fixture_mode:
            tasks.add_task(_execute, db, run_id, asset, fixtures_dir(request))
        else:
            tasks.add_task(_execute_live, db, run_id, text, live)
        return RunCreated(run_id=run_id, status="running")

    @app.get("/runs")
    def runs(request: Request, limit: int = Query(20, ge=1, le=100)) -> list[RunSummary]:
        with database(request) as conn:
            return [report.run_summary(r) for r in list_runs(conn, limit)]

    @app.get("/runs/{run_id}")
    def run(run_id: str, request: Request) -> RunSummary:
        with database(request) as conn:
            record = get_run(conn, run_id)
        if record is None:
            raise HTTPException(404, f"run {run_id} not found")
        return report.run_summary(record)

    @app.get("/runs/{run_id}/report")
    def run_report(run_id: str, request: Request) -> ReportResponse:
        with database(request) as conn:
            try:
                return report.build_report(conn, run_id)
            except report.RunNotFoundError as exc:
                raise _not_found(exc) from exc
            except report.RunNotReadyError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/runs/{run_id}/resolver")
    def run_resolver(run_id: str, request: Request) -> ResolverOutput:
        with database(request) as conn:
            try:
                return report.get_resolver(conn, run_id)
            except report.RunNotFoundError as exc:
                raise _not_found(exc) from exc
            except report.RunNotReadyError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/runs/{run_id}/evidence")
    def run_evidence(run_id: str, request: Request) -> list[EvidenceView]:
        """Every evidence item of the run's bundle; the report lists only the cited ones."""
        with database(request) as conn:
            try:
                return report.list_evidence(conn, run_id)
            except report.RunNotFoundError as exc:
                raise _not_found(exc) from exc
            except report.RunNotReadyError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/runs/{run_id}/market")
    def run_market(run_id: str, request: Request) -> MarketResponse:
        """Patients, analog price and market size, computed by code from the bundle."""
        with database(request) as conn:
            try:
                return report.build_market(conn, run_id)
            except report.RunNotFoundError as exc:
                raise _not_found(exc) from exc
            except report.RunNotReadyError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/runs/{run_id}/financials")
    def run_financials(run_id: str, request: Request) -> FinancialsResponse:
        """PoS, rNPV, capital, time to milestone and tornado, computed by code from the bundle."""
        with database(request) as conn:
            try:
                return report.build_financials(conn, run_id)
            except report.RunNotFoundError as exc:
                raise _not_found(exc) from exc
            except report.RunNotReadyError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/runs/{run_id}/claims/{claim_id}")
    def claim(run_id: str, claim_id: str, request: Request) -> ClaimView:
        with database(request) as conn:
            try:
                return report.get_claim(conn, run_id, claim_id)
            except (report.RunNotFoundError, report.ItemNotFoundError) as exc:
                raise _not_found(exc) from exc

    @app.get("/runs/{run_id}/evidence/{evidence_id}")
    def evidence(run_id: str, evidence_id: str, request: Request) -> EvidenceView:
        with database(request) as conn:
            try:
                return report.get_evidence(conn, run_id, evidence_id)
            except (report.RunNotFoundError, report.ItemNotFoundError) as exc:
                raise _not_found(exc) from exc

    @app.get("/runs/{run_id}/trace")
    def trace(run_id: str, request: Request) -> TraceResponse:
        with database(request) as conn:
            try:
                return report.build_trace(conn, run_id)
            except report.RunNotFoundError as exc:
                raise _not_found(exc) from exc

    @app.post("/runs/{run_id}/evidence", status_code=202)
    def add_evidence(
        run_id: str, body: AddEvidenceRequest, tasks: BackgroundTasks, request: Request
    ) -> RunCreated:
        """Recompute a finished run on added evidence, as a new run with the next bundle version.

        Compare the two with `GET /runs/{new id}/diff`.
        """
        if llm is None:
            if settings.use_fixtures():
                raise HTTPException(
                    422,
                    "fixture runs answer from prepared model drafts and cannot reason over new "
                    "evidence; use a live API, or compare two runs with /runs/{id}/diff?against=",
                )
            try:
                require_configured()
            except ConfigError as exc:
                raise HTTPException(503, str(exc)) from exc
        added = [
            analyst_evidence(
                number, e.text, e.url, e.source, e.source_kind, e.level, e.published_at
            )
            for number, e in enumerate(body.evidence, start=1)
        ]
        new_id, db = new_run_id(), request.app.state.db_path
        with database(request) as conn:
            try:
                prepare_recompute(conn, run_id, new_id, added, body.as_of)
            except RecomputeError as exc:
                raise HTTPException(422, str(exc)) from exc
            except LookupError as exc:
                raise _not_found(exc) from exc
        tasks.add_task(_execute_recompute, db, new_id, llm)
        return RunCreated(run_id=new_id, status="running")

    @app.get("/runs/{run_id}/diff")
    def run_diff(run_id: str, request: Request, against: str | None = None) -> DiffResponse:
        """What changed in this run compared with `against` (default: the run it grew from)."""
        with database(request) as conn:
            try:
                base = against or report.run_summary(report.require_run(conn, run_id)).input.get(
                    PARENT
                )
                if not base:
                    raise HTTPException(422, "say which run to compare with: ?against=<run id>")
                return build_diff(conn, base, run_id)
            except report.RunNotFoundError as exc:
                raise _not_found(exc) from exc
            except report.RunNotReadyError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/runs/{run_id}/events")
    async def events(run_id: str, request: Request) -> StreamingResponse:
        """Server-sent events: every step of the run, then `end`. Reconnect with Last-Event-ID."""
        db = request.app.state.db_path
        after = int(request.headers.get("last-event-id", "0") or 0)
        exists = await run_in_threadpool(_run_status, db, run_id)
        if exists is None:
            raise HTTPException(404, f"run {run_id} not found")
        return StreamingResponse(
            _stream(db, run_id, after),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _execute(db_path: Path | None, run_id: str, asset: str, fixtures: Path) -> None:
    with closing(settings.open_database(db_path)) as conn:
        run_fixture(conn, run_id, asset, fixtures)


def _execute_live(db_path: Path | None, run_id: str, text: str, live: LiveRunner | None) -> None:
    with closing(settings.open_database(db_path)) as conn:
        if live is not None:
            live(conn, run_id, text)
        else:
            run_live(conn, run_id, text, lambda run: live_llm(run, db_path))


def _execute_recompute(db_path: Path | None, run_id: str, llm: LLMFactory | None) -> None:
    with closing(settings.open_database(db_path)) as conn:
        finish_recompute(
            conn,
            run_id,
            lambda: load_bundle(conn, run_id),
            lambda: llm(run_id) if llm is not None else live_llm(run_id, db_path),
            settings.recompute_mode(),
        )


def _run_status(db_path: Path | None, run_id: str) -> str | None:
    with closing(settings.open_database(db_path)) as conn:
        record = get_run(conn, run_id)
    return None if record is None else record.status


def _poll(db_path: Path | None, run_id: str, after: int) -> tuple[list[dict], bool]:
    with closing(settings.open_database(db_path)) as conn:
        fresh = load_events(conn, run_id, after)
        record = get_run(conn, run_id)
    payload = [
        {
            "seq": e.seq,
            "step": e.step,
            "status": e.status,
            "detail": e.detail,
            "created_at": e.created_at.isoformat(),
        }
        for e in fresh
    ]
    finished = record is not None and record.status in {DONE, FAILED}
    return payload, finished


async def _stream(db_path: Path | None, run_id: str, after: int) -> AsyncIterator[str]:
    idle = 0.0
    while True:
        fresh, finished = await run_in_threadpool(_poll, db_path, run_id, after)
        for event in fresh:
            after = event["seq"]
            yield f"id: {event['seq']}\nevent: {event['step']}\ndata: {json.dumps(event)}\n\n"
        if finished and not fresh:
            yield f"event: end\ndata: {json.dumps({'run_id': run_id})}\n\n"
            return
        idle = 0.0 if fresh else idle + POLL_SECONDS
        if idle >= KEEPALIVE_SECONDS:
            yield ": keepalive\n\n"
            idle = 0.0
        await asyncio.sleep(POLL_SECONDS)


app = create_app()
