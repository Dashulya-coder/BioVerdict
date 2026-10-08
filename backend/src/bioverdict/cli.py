"""Underwriting runs from the command line, with the same pipeline and report as the API.

Fixture runs (the default) are offline and free. `USE_FIXTURES=0` makes the run live: public
sources are read and the configured model is called, which costs money.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path
from uuid import uuid4

from bioverdict import settings
from bioverdict.api.report import build_report
from bioverdict.llm.errors import ConfigError
from bioverdict.pipeline.fixture_run import fixture_names, run_fixture
from bioverdict.pipeline.live_llm import live_llm, require_configured
from bioverdict.pipeline.live_run import LiveRunner, run_live
from bioverdict.store.runs_repo import create_run, load_events


def main(argv: list[str] | None = None, live: LiveRunner | None = None) -> int:
    """`live` replaces the real live pipeline (sources and model); tests pass a stand-in."""
    parser = argparse.ArgumentParser(prog="bioverdict", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="underwrite one asset or one indication and mechanism")
    subject = run.add_mutually_exclusive_group(required=True)
    subject.add_argument("--asset", help="drug name or code (a fixture name in fixture mode)")
    subject.add_argument("--query", help='live runs only: free text, e.g. "KRAS G12C in NSCLC"')
    run.add_argument("--as-of", type=date.fromisoformat, default=settings.today())
    run.add_argument("--db", type=Path, help="SQLite path; defaults to DB_PATH")
    run.add_argument("--fixtures", type=Path, help="fixture directory; defaults to FIXTURES_DIR")
    run.add_argument("--output", type=Path, help="also write the JSON report to this file")
    args = parser.parse_args(argv)

    fixture_mode = settings.use_fixtures()
    fixtures = args.fixtures if args.fixtures is not None else settings.fixtures_dir()
    text = (args.asset or args.query).strip()
    if fixture_mode:
        if args.query is not None:
            parser.error("--query needs a live run; set USE_FIXTURES=0")
        text = text.casefold()
        known = fixture_names(fixtures)
        if text not in known:
            parser.error(f"no fixture for {text!r}; available: {', '.join(known) or 'none'}")
    else:
        if not text:
            parser.error("the asset or query is empty")
        if live is None:
            try:
                require_configured()
            except ConfigError as exc:
                parser.error(str(exc))

    run_id = f"R-{uuid4().hex}"
    mode = "offline, no paid model calls" if fixture_mode else "live sources and paid model calls"
    print(f"Run {run_id}: {mode}.", file=sys.stderr)
    request = {"asset" if args.asset else "query": text, "as_of": args.as_of.isoformat()}
    try:
        with closing(settings.open_database(args.db)) as conn:
            create_run(conn, run_id, request, args.as_of)
            if fixture_mode:
                result = run_fixture(conn, run_id, text, fixtures)
            elif live is not None:
                result = live(conn, run_id, text)
            else:
                result = run_live(conn, run_id, text, lambda run: live_llm(run, args.db))
            if result is None:
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
