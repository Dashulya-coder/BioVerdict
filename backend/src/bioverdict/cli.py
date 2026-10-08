"""Underwriting runs from the command line, with the same pipeline and report as the API.

Fixture runs (the default) are offline and free. `USE_FIXTURES=0` makes the run live: public
sources are read and the configured model is called, which costs money. `eval` runs the
regression cases the same way; `warm` only reads the public sources, which is free.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path
from uuid import uuid4

from bioverdict import settings
from bioverdict.api.report import build_report
from bioverdict.eval.cases import load_cases
from bioverdict.eval.runner import StartRun, run_cases, summary, write_report
from bioverdict.eval.warm import load_assets, table, warm
from bioverdict.llm.errors import ConfigError
from bioverdict.pipeline.fixture_run import fixture_names, run_fixture
from bioverdict.pipeline.live_llm import live_llm, require_configured
from bioverdict.pipeline.live_run import LiveRunner, run_live
from bioverdict.pipeline.live_sources import SourcesFactory, paced_sources
from bioverdict.store.runs_repo import create_run, load_events


def main(
    argv: list[str] | None = None,
    live: LiveRunner | None = None,
    sources: SourcesFactory | None = None,
) -> int:
    """`live` replaces the real live pipeline (sources and model) and `sources` what `warm`
    reads; tests pass stand-ins."""
    parser = argparse.ArgumentParser(prog="bioverdict", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="underwrite one asset or one indication and mechanism")
    subject = run.add_mutually_exclusive_group(required=True)
    subject.add_argument("--asset", help="drug name or code (a fixture name in fixture mode)")
    subject.add_argument("--query", help='live runs only: free text, e.g. "KRAS G12C in NSCLC"')
    run.add_argument("--as-of", type=date.fromisoformat, default=settings.today())
    run.add_argument("--output", type=Path, help="also write the JSON report to this file")

    evaluate = commands.add_parser("eval", help="run the regression cases and report metrics")
    evaluate.add_argument("--cases", type=Path, required=True, help="YAML file of cases")
    evaluate.add_argument("--out", type=Path, required=True, help="directory for the results")
    evaluate.add_argument("--repeat", type=int, default=1, help="runs per case (stability)")

    warming = commands.add_parser("warm", help="cache the public sources for a list of assets")
    warming.add_argument(
        "--list", type=Path, required=True, help="name, indication, targets by tabs"
    )
    warming.add_argument("--as-of", type=date.fromisoformat, default=settings.today())
    warming.add_argument("--output", type=Path, help="also write the result as JSON")
    warming.add_argument(
        "--refresh", action="store_true", help="download again what is already cached"
    )

    for command in (run, evaluate, warming):
        command.add_argument("--db", type=Path, help="SQLite path; defaults to DB_PATH")
    for command in (run, evaluate):
        command.add_argument("--fixtures", type=Path, help="fixture directory (FIXTURES_DIR)")
    args = parser.parse_args(argv)

    if args.command == "warm":
        patient = paced_sources(WARM_INTERVAL_S, WARM_ATTEMPTS, refresh=args.refresh)
        return _warm(parser, args, sources or patient)
    fixture_mode = settings.use_fixtures()
    fixtures = args.fixtures if args.fixtures is not None else settings.fixtures_dir()
    if not fixture_mode and live is None:
        try:
            require_configured()
        except ConfigError as exc:
            parser.error(str(exc))
    start = _starter(fixture_mode, fixtures, live, args.db)
    if args.command == "eval":
        return _eval(parser, args, start, fixture_mode)

    text = (args.asset or args.query).strip()
    if fixture_mode:
        if args.query is not None:
            parser.error("--query needs a live run; set USE_FIXTURES=0")
        text = text.casefold()
        known = fixture_names(fixtures)
        if text not in known:
            parser.error(f"no fixture for {text!r}; available: {', '.join(known) or 'none'}")
    elif not text:
        parser.error("the asset or query is empty")

    run_id = f"R-{uuid4().hex}"
    print(f"Run {run_id}: {_mode_note(fixture_mode)}.", file=sys.stderr)
    request = {"asset" if args.asset else "query": text, "as_of": args.as_of.isoformat()}
    try:
        with closing(settings.open_database(args.db)) as conn:
            create_run(conn, run_id, request, args.as_of)
            if start(conn, run_id, text) is None:
                print(f"{run_id} failed: {load_events(conn, run_id)[-1].detail}", file=sys.stderr)
                return 1
            payload = build_report(conn, run_id).model_dump_json(indent=2) + "\n"
        if args.output is not None:
            args.output.write_text(payload, encoding="utf-8")
        sys.stdout.write(payload)
    except (OSError, sqlite3.Error) as exc:
        print(f"{run_id}: {exc}", file=sys.stderr)
        return 1
    return 0


# Many assets in a row: one request a second and more patience keep the registry from refusing.
WARM_INTERVAL_S = 1.0
WARM_ATTEMPTS = 5


def _mode_note(fixture_mode: bool) -> str:
    return "offline, no paid model calls" if fixture_mode else "live sources and paid model calls"


def _starter(
    fixture_mode: bool, fixtures: Path, live: LiveRunner | None, db: Path | None
) -> StartRun:
    """How a run is carried out in the current mode: from fixtures, or live."""
    if fixture_mode:
        return lambda conn, run_id, text: run_fixture(conn, run_id, text.casefold(), fixtures)
    if live is not None:
        return live
    return lambda conn, run_id, text: run_live(conn, run_id, text, lambda run: live_llm(run, db))


def _eval(
    parser: argparse.ArgumentParser, args: argparse.Namespace, start: StartRun, fixture_mode: bool
) -> int:
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError) as exc:
        parser.error(f"cases cannot be read: {exc}")
    print(
        f"{len(cases)} case(s), {args.repeat} run(s) each: {_mode_note(fixture_mode)}.",
        file=sys.stderr,
    )
    try:
        with closing(settings.open_database(args.db)) as conn:
            report = run_cases(
                conn,
                cases,
                start,
                mode="fixtures" if fixture_mode else "live",
                repeat=args.repeat,
                today=settings.today(),
            )
        write_report(report, args.out)
    except (OSError, sqlite3.Error) as exc:
        print(f"eval: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(summary(report))
    unexpected = [c.case_id for c in report.cases if c.verdict_as_expected is False]
    failed = [c.case_id for c in report.cases if any(r.failure for r in c.runs)]
    if unexpected or failed:
        print(
            f"unexpected verdict: {', '.join(unexpected) or 'none'}; "
            f"failed runs: {', '.join(failed) or 'none'}",
            file=sys.stderr,
        )
        return 1
    return 0


def _warm(
    parser: argparse.ArgumentParser, args: argparse.Namespace, sources: SourcesFactory
) -> int:
    try:
        assets = load_assets(args.list)
    except (OSError, ValueError) as exc:
        parser.error(f"list cannot be read: {exc}")
    print(f"Warming {len(assets)} asset(s): public sources only, no model calls.", file=sys.stderr)
    try:
        with closing(settings.open_database(args.db)) as conn:
            results = asyncio.run(warm(conn, assets, sources, args.as_of))
        if args.output is not None:
            payload = json.dumps([r.model_dump() for r in results], indent=2, ensure_ascii=False)
            args.output.write_text(payload + "\n", encoding="utf-8")
    except (OSError, sqlite3.Error) as exc:
        print(f"warm: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(table(results))
    return 1 if any(r.error or r.problems for r in results) else 0
