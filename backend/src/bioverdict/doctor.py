"""`bioverdict doctor`: is this machine ready for a run? (A11)

Checks the mode, the model configuration, the database, the caches, the fixtures and, unless
asked not to, whether the three public sources answer. It never calls a model, so it is free; a
key that is set is not proven to be valid. Secrets are never printed, only whether they are set.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx

from bioverdict import settings
from bioverdict.llm import ConfigError, LLMConfig
from bioverdict.pipeline.fixture_run import fixture_names
from bioverdict.pipeline.live_llm import KEY
from bioverdict.store.bundle import compute_content_hash
from bioverdict.store.migrations import SCHEMA_VERSION, current_version
from bioverdict.store.models import Bundle

Status = Literal["ok", "warn", "fail"]
PYTHON = (3, 14)
PROBE_TIMEOUT_S = 15


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


# Asks one public source whether it is up and returns a short note; raises when it is not.
Probe = Callable[[httpx.Client], str]


def _clinicaltrials(client: httpx.Client) -> str:
    answer = client.get("https://clinicaltrials.gov/api/v2/version")
    answer.raise_for_status()
    return f"data as of {answer.json()['dataTimestamp']}"


def _opentargets(client: httpx.Client) -> str:
    query = {"query": "{ meta { dataVersion { year month } } }"}
    answer = client.post("https://api.platform.opentargets.org/api/v4/graphql", json=query)
    answer.raise_for_status()
    version = answer.json()["data"]["meta"]["dataVersion"]
    return f"release {version['year']}.{version['month']}"


def _pubmed(client: httpx.Client) -> str:
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi"
    answer = client.get(url, params={"db": "pubmed", "retmode": "json"})
    answer.raise_for_status()
    answer.json()["einforesult"]  # an error page would not have it
    return "answers"


SOURCES: dict[str, Probe] = {
    "ClinicalTrials.gov": _clinicaltrials,
    "Open Targets": _opentargets,
    "PubMed": _pubmed,
}


def check_python() -> Check:
    found = sys.version_info[:3]
    text = ".".join(map(str, found))
    if found[:2] == PYTHON:
        return Check("python", "ok", text)
    return Check("python", "warn", f"{text}; the project is developed on {PYTHON[0]}.{PYTHON[1]}")


def check_mode_and_model() -> list[Check]:
    live = not settings.use_fixtures()
    mode = Check(
        "mode",
        "ok",
        "live: runs read public sources and call the model (paid)"
        if live
        else "fixtures: runs are answered offline (set USE_FIXTURES=0 for live runs)",
    )
    has_key = bool(os.environ.get(KEY))
    if has_key:
        key = Check("model key", "ok", f"{KEY} is set (not verified: no model is called)")
    elif live:
        key = Check("model key", "fail", f"{KEY} is not set: a live run cannot start")
    else:
        key = Check("model key", "warn", f"{KEY} is not set: fine for fixtures, not for live runs")
    try:
        config = LLMConfig.default()
        limits = Check(
            "run limits",
            "ok",
            f"budget ${config.budget_usd:.2f}, deadline {config.run_timeout_s:.0f} s per run",
        )
    except (ConfigError, ValueError) as exc:
        limits = Check("run limits", "fail", f"RUN_BUDGET_USD or RUN_TIMEOUT_S is invalid: {exc}")
    return [mode, key, limits]


def check_database(path: Path | None) -> Check:
    target = path or settings.db_path()
    existed = target.exists()
    try:
        with closing(settings.open_database(target)) as conn:
            version = current_version(conn)
            runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            with conn:  # proves the file can be written, and leaves nothing behind
                conn.execute("CREATE TABLE doctor_probe (x INTEGER)")
                conn.execute("DROP TABLE doctor_probe")
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        return Check("database", "fail", f"{target}: {type(exc).__name__}: {exc}")
    state = "opened" if existed else "created"
    return Check(
        "database", "ok", f"{target}: {state}, schema {version}/{SCHEMA_VERSION}, {runs} run(s)"
    )


def check_http_cache(path: Path | None) -> Check:
    try:
        with closing(settings.open_database(path)) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n, MIN(fetched_at) AS oldest, MAX(fetched_at) AS newest "
                "FROM http_cache"
            ).fetchone()
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        return Check("source cache", "fail", f"{type(exc).__name__}: {exc}")
    try:
        max_age = settings.http_cache_max_age_s()
    except ValueError:
        return Check("source cache", "fail", "HTTP_CACHE_MAX_AGE_H is not a number")
    policy = (
        "answers never expire" if max_age is None else f"answers expire after {max_age / 3600:g} h"
    )
    if not row["n"]:
        return Check(
            "source cache", "warn", f"empty: the first live run downloads everything; {policy}"
        )
    oldest = datetime.fromisoformat(row["oldest"]).date()
    newest = datetime.fromisoformat(row["newest"]).date()
    return Check(
        "source cache", "ok", f"{row['n']} answers, downloaded {oldest} to {newest}; {policy}"
    )


def check_model_cache() -> Check:
    directory = settings.cache_dir() / "llm"
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory):
            pass
    except OSError as exc:
        return Check("model cache", "fail", f"{directory} cannot be written: {type(exc).__name__}")
    answers = sum(1 for _ in directory.glob("*.json"))
    return Check("model cache", "ok", f"{directory}: writable, {answers} cached answer(s)")


def check_fixtures(directory: Path | None) -> Check:
    fixtures = directory or settings.fixtures_dir()
    names = fixture_names(fixtures)
    if not names:
        return Check(
            "fixtures", "fail", f"{fixtures}: no complete fixture (bundle, resolver, reasoning)"
        )
    for name in names:
        try:
            text = (fixtures / "bundles" / f"{name}.json").read_text(encoding="utf-8")
            bundle = Bundle.model_validate_json(text)
        except (OSError, ValueError) as exc:
            return Check(
                "fixtures", "fail", f"{name}: bundle cannot be read ({type(exc).__name__})"
            )
        if compute_content_hash(bundle.evidence, bundle.section_statuses) != bundle.content_hash:
            return Check("fixtures", "fail", f"{name}: content_hash does not match the evidence")
    return Check("fixtures", "ok", f"{fixtures}: {', '.join(names)}; hashes match")


def check_sources(sources: dict[str, Probe] | None = None) -> list[Check]:
    """One small request to each public source, outside the cache."""
    checks = []
    with httpx.Client(timeout=PROBE_TIMEOUT_S) as client:
        for name, probe in (sources or SOURCES).items():
            try:
                checks.append(Check(name, "ok", probe(client)))
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                # A status code is safe to show; the rest of a failure is only named.
                code = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
                reason = f"HTTP {code}" if code else type(exc).__name__
                checks.append(Check(name, "fail", f"did not answer as expected ({reason})"))
    return checks


def run_checks(
    db: Path | None = None,
    fixtures: Path | None = None,
    *,
    offline: bool = False,
    sources: dict[str, Probe] | None = None,
) -> list[Check]:
    checks = [check_python(), *check_mode_and_model(), check_database(db)]
    checks += [check_http_cache(db), check_model_cache(), check_fixtures(fixtures)]
    if offline:
        checks.append(Check("sources", "warn", "not checked (--offline)"))
    else:
        checks += check_sources(sources)
    return checks


def render(checks: list[Check]) -> str:
    width = max(len(check.name) for check in checks)
    lines = [f"{check.status:<4}  {check.name:<{width}}  {check.detail}" for check in checks]
    counts = {status: sum(c.status == status for c in checks) for status in ("ok", "warn", "fail")}
    lines.append(f"{counts['ok']} ok, {counts['warn']} warn, {counts['fail']} fail")
    return "\n".join(lines) + "\n"
