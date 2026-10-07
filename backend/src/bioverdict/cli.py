"""Offline fixture runs using the same pipeline and report as the API."""

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
from bioverdict.pipeline.fixture_run import fixture_names, run_fixture
from bioverdict.store.runs_repo import create_run, load_events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bioverdict", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run fixtures without network or paid model calls")
    run.add_argument("--asset", required=True, help="fixture asset name (e.g. divarasib)")
    run.add_argument("--as-of", type=date.fromisoformat, default=settings.today())
    run.add_argument("--db", type=Path, help="SQLite path; defaults to DB_PATH")
    run.add_argument("--fixtures", type=Path, help="fixture directory; defaults to FIXTURES_DIR")
    run.add_argument("--output", type=Path, help="also write the JSON report to this file")
    args = parser.parse_args(argv)

    if not settings.use_fixtures():
        parser.error("live runs are not wired in; set USE_FIXTURES=1")
    fixtures = args.fixtures if args.fixtures is not None else settings.fixtures_dir()
    asset = args.asset.strip().casefold()
    known = fixture_names(fixtures)
    if asset not in known:
        parser.error(f"no fixture for {asset!r}; available: {', '.join(known) or 'none'}")

    run_id = f"R-{uuid4().hex}"
    print(f"Fixture run {run_id}: offline, no paid model calls.", file=sys.stderr)
    try:
        with closing(settings.open_database(args.db)) as conn:
            create_run(conn, run_id, {"asset": asset, "as_of": args.as_of.isoformat()}, args.as_of)
            if run_fixture(conn, run_id, asset, fixtures) is None:
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
