"""A live run with every outside party replaced: recorded Open Targets answers for the Resolver,
the divarasib bundle as the only source, canned model answers. No network, no key."""

import asyncio
import json
import re
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
import pytest
from resolver.recorded import make_lookup

from bioverdict.agents.collect import CollectPlan
from bioverdict.connectors.fake import FakeConnector
from bioverdict.contracts import Connector
from bioverdict.llm import ConfigError, FakeLLM
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.pipeline.live_llm import live_llm
from bioverdict.pipeline.live_run import describe_request, run_live
from bioverdict.pipeline.live_sources import (
    CLASS_STUDIES,
    LIVE_PLANS,
    Sources,
    TargetClassTrials,
    class_records,
)
from bioverdict.store.db import connect
from bioverdict.store.evidence_ids import assign_ids
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Asset,
    Basis,
    Bundle,
    Evidence,
    Indication,
    ResolverOutput,
    Section,
    SectionStatus,
    Target,
)
from bioverdict.store.runs_repo import (
    DONE,
    FAILED,
    create_run,
    get_run,
    load_claims,
    load_events,
)

FIXTURES = Path(__file__).parents[3] / "fixtures"
AS_OF = date(2026, 10, 7)
BUNDLE = Bundle.model_validate_json(
    (FIXTURES / "bundles" / "divarasib.json").read_text(encoding="utf-8")
)
FORM = {"drug_names": ["divarasib"], "indication": "NSCLC", "targets": ["KRAS"]}
PLANS = (CollectPlan(section=Section.CLINICAL, tools=("fixture",)),)


class Broken:
    """A source that cannot be reached."""

    name = "fixture"

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def fetch(self, query: ResolverOutput, as_of: date) -> list:
        raise self._error


def answers(form: dict = FORM) -> dict:
    """The model copies every source whole, then answers as in the divarasib fixture.

    Freezing numbers evidence anew, so the canned drafts are rewritten to the ids the same
    excerpts get in the run's bundle.
    """
    # A status fact reaches the bundle as retrieved; the model is asked about the rest.
    facts = [{"source_id": e.id, "quote": e.excerpt} for e in BUNDLE.evidence if not e.status_key]
    old_ids = {(e.url, e.excerpt): e.id for e in BUNDLE.evidence}
    new_ids = {old_ids[e.url, e.excerpt]: e.id for e in assign_ids([], BUNDLE.evidence, 1)}
    drafts = (FIXTURES / "reasoning" / "divarasib.json").read_text(encoding="utf-8")
    reasoning = json.loads(re.sub(r"E-\d{4}", lambda found: new_ids[found.group()], drafts))
    return {"resolver": form, "extraction": {"facts": facts}, **reasoning}


def sources(tmp_path: Path, tool: Connector | None = None):
    @asynccontextmanager
    async def opened(conn: sqlite3.Connection) -> AsyncIterator[Sources]:
        yield Sources(
            lookup=make_lookup(tmp_path),
            tools={"fixture": tool or FakeConnector(BUNDLE.evidence, name="fixture")},
            plans=PLANS,
        )

    return opened


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "run.db")
    migrate(connection)
    yield connection
    connection.close()


def live(conn, tmp_path, llm=None, tool=None, as_of=AS_OF, run_id="R-1"):
    create_run(conn, run_id, {"asset": "divarasib"}, as_of)
    model = llm or FakeLLM(answers())
    return model, run_live(conn, run_id, "divarasib", lambda _: model, sources(tmp_path, tool))


def last_event(conn: sqlite3.Connection, run_id: str = "R-1"):
    return load_events(conn, run_id)[-1]


def test_a_live_run_records_the_same_steps_as_a_fixture_run(conn, tmp_path) -> None:
    _, result = live(conn, tmp_path)

    run = get_run(conn, "R-1")
    assert result is not None and run is not None and run.status == DONE and run.result == result
    assert [(e.step, e.status) for e in load_events(conn, "R-1")] == [
        ("resolve", "started"),
        ("resolve", "done"),
        ("collect", "started"),
        ("collect", "done"),
        ("freeze", "started"),
        ("freeze", "done"),
        ("reason", "started"),
        ("reason", "done"),
        ("score", "started"),
        ("score", "done"),
        ("run", "done"),
    ]


def test_ids_come_from_the_lookup_and_the_bundle_from_the_sources(conn, tmp_path) -> None:
    live(conn, tmp_path)

    run, bundle = get_run(conn, "R-1"), load_bundle(conn, "R-1")
    assert run is not None and run.resolver is not None
    assert run.resolver.assets[0].chembl_id == "CHEMBL5095236"
    assert run.resolver.targets[0].ensembl == "ENSG00000133703"
    assert {e.excerpt for e in bundle.evidence} == {e.excerpt for e in BUNDLE.evidence}
    assert bundle.section_statuses[Section.CLINICAL] is SectionStatus.FOUND


def test_only_planned_sections_are_reported_as_searched(conn, tmp_path) -> None:
    live(conn, tmp_path)

    statuses = load_bundle(conn, "R-1").section_statuses
    unplanned = [s for s in Section if s is not Section.CLINICAL]
    assert all(statuses[s] is SectionStatus.NOT_SEARCHED for s in unplanned)


def test_the_same_evidence_gives_the_verdict_of_the_fixture_run(conn, tmp_path) -> None:
    _, result = live(conn, tmp_path)
    create_run(conn, "R-fixture", {"asset": "divarasib"}, AS_OF)

    expected = run_fixture(conn, "R-fixture", "divarasib", FIXTURES)

    assert result is not None and expected is not None
    assert (result.verdict, result.confidence) == (expected.verdict, expected.confidence)


def test_the_model_works_through_the_steps_in_order_and_never_resolves_twice(
    conn, tmp_path
) -> None:
    model, _ = live(conn, tmp_path)

    steps = [step for step, _ in model.calls]
    assert steps[:2] == ["resolver", "extraction"]
    assert steps[2:] and all(step.startswith("reasoning.") for step in steps[2:])


def test_an_input_without_a_target_fails_with_the_reason(conn, tmp_path) -> None:
    model = FakeLLM(answers({"drug_names": [], "targets": []}))

    _, result = live(conn, tmp_path, llm=model)

    run, last = get_run(conn, "R-1"), last_event(conn)
    assert result is None and run is not None and run.status == FAILED
    assert (last.step, last.status) == ("run", "failed") and "no target" in last.detail
    assert [step for step, _ in model.calls] == ["resolver"]  # nothing was collected or reasoned


def test_unreachable_sources_fail_the_run_instead_of_an_empty_report(conn, tmp_path) -> None:
    model, result = live(conn, tmp_path, tool=Broken(httpx.ConnectError("down")))

    run, last = get_run(conn, "R-1"), last_event(conn)
    assert result is None and run is not None and run.status == FAILED
    assert "no evidence was collected" in last.detail and "clinical" in last.detail
    assert not any(step.startswith("reasoning.") for step, _ in model.calls)
    with pytest.raises(LookupError):
        load_bundle(conn, "R-1")


def test_an_unexpected_error_is_named_but_its_text_is_not_stored(conn, tmp_path) -> None:
    _, result = live(conn, tmp_path, tool=Broken(RuntimeError("token sk-secret leaked")))

    assert result is None and last_event(conn).detail == "RuntimeError"


def test_a_missing_model_key_fails_the_run_with_the_reason(conn, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    create_run(conn, "R-1", {"asset": "divarasib"}, AS_OF)

    result = run_live(conn, "R-1", "divarasib", live_llm, sources(tmp_path))

    assert result is None and "ANTHROPIC_API_KEY" in last_event(conn).detail
    with pytest.raises(ConfigError):
        live_llm("R-1")


def test_a_cutoff_before_all_evidence_is_an_honest_empty_run(conn, tmp_path) -> None:
    _, result = live(conn, tmp_path, as_of=date(2000, 1, 1))

    bundle, (claims, links) = load_bundle(conn, "R-1"), load_claims(conn, "R-1")
    assert result is not None and bundle.evidence == [] and links == []
    assert bundle.section_statuses[Section.CLINICAL] is SectionStatus.NONE_FOUND
    assert claims and all(c.basis is Basis.UNKNOWN for c in claims)
    assert "none_found" in next(
        e.detail for e in load_events(conn, "R-1") if (e.step, e.status) == ("collect", "done")
    )


@pytest.mark.parametrize(
    "fields,text",
    [
        (("divarasib", None, None), "divarasib"),
        ((None, "NSCLC", "KRAS G12C inhibitor"), "KRAS G12C inhibitor for NSCLC"),
        (
            (" HRO761 ", "MSI-high tumors", "WRN inhibitor"),
            "HRO761: WRN inhibitor for MSI-high tumors",
        ),
        ((None, " ", ""), ""),
    ],
)
def test_a_request_is_put_to_the_resolver_as_one_line(fields, text) -> None:
    assert describe_request(*fields) == text


class Registry:
    """Remembers what the registry was asked."""

    def __init__(self) -> None:
        self.asked: list[ResolverOutput] = []
        self.problems: list[str] = []

    async def fetch(self, query: ResolverOutput, as_of: date) -> list:
        self.asked.append(query)
        return []


def by_asset(indication: str) -> ResolverOutput:
    return ResolverOutput(
        indication=Indication(name=indication),
        targets=[Target(symbol="KRAS")],
        known_assets=["divarasib"],
        assets=[Asset(name="DIVARASIB", chembl_id="CHEMBL5095236")],
    )


async def test_the_class_search_asks_the_registry_about_the_target_not_the_asset() -> None:
    registry = Registry()

    await TargetClassTrials(registry).fetch(by_asset("NSCLC"), AS_OF)

    (asked,) = registry.asked
    assert (asked.known_assets, asked.assets) == ([], [])
    assert (asked.indication.name, asked.targets[0].symbol) == ("NSCLC", "KRAS")


async def test_the_class_search_needs_an_indication() -> None:
    registry = Registry()

    assert await TargetClassTrials(registry).fetch(by_asset("not specified"), AS_OF) == []
    assert registry.asked == []


def test_every_live_plan_names_a_section_once() -> None:
    sections = [plan.section for plan in LIVE_PLANS]
    assert len(sections) == len(set(sections)) and Section.TRANSLATION not in sections


def test_the_competition_section_reads_the_registry_class_and_the_fda() -> None:
    plans = {plan.section: plan.tools for plan in LIVE_PLANS}

    assert plans[Section.COMPETITION] == ("clinicaltrials_class", "openfda")


def study(nct: str, status: str, phase: str, updated: date) -> list[Evidence]:
    """The records the registry connector gives for one study, reduced to what matters here."""
    shared = {
        "source": "ClinicalTrials.gov",
        "source_family": "registry",
        "source_kind": "registry",
        "url": f"https://clinicaltrials.gov/study/{nct}",
        "locator": {"type": "nct", "value": nct},
        "published_at": updated,
        "retrieved_at": "2026-10-06T00:00:00Z",
        "level": "registry_record",
        "independence_group": "sponsor:x",
        "version": 1,
    }
    parts = {
        "summary": ("A study of a drug.", None),
        "status": (f'{{"overallStatus": "{status}"}}', f"nct:{nct}:overall_status"),
        "design": (f'{{"phases": ["{phase}"]}}', f"nct:{nct}:design"),
    }
    return [
        Evidence.model_validate(
            {**shared, "id": f"{nct}:{part}", "excerpt": text, "status_key": key}
        )
        for part, (text, key) in parts.items()
    ]


def test_a_class_search_keeps_the_status_and_design_of_each_study_only() -> None:
    kept = class_records(study("NCT1", "RECRUITING", "PHASE3", date(2026, 1, 1)))

    assert [e.id for e in kept] == ["NCT1:status", "NCT1:design"]


def test_a_class_search_keeps_stopped_and_running_studies_latest_phase_and_newest_first() -> None:
    records = []
    for number in range(20):
        records += study(f"NCT-RUN-{number:02d}", "RECRUITING", "PHASE1", date(2020, 1, number + 1))
    records += study("NCT-OLD-P3", "COMPLETED", "PHASE3", date(2015, 1, 1))
    records += study("NCT-STOP-P2", "TERMINATED", "PHASE2", date(2016, 1, 1))
    records += study("NCT-STOP-P1", "WITHDRAWN", "PHASE1", date(2025, 1, 1))

    kept = [e.locator.value for e in class_records(records) if e.locator and "status" in e.id]

    assert kept[:2] == ["NCT-STOP-P2", "NCT-STOP-P1"]  # stopped: a failed analog is never cut
    assert kept[2] == "NCT-OLD-P3"  # then the latest phase, however old
    assert kept[3] == "NCT-RUN-19" and len(kept) == 2 + CLASS_STUDIES  # then the newest
    assert len(class_records(records)) <= 50  # inside the per-source record limit


class Slow:
    """A source that answers after the section's deadline."""

    name = "fixture"

    async def fetch(self, query: ResolverOutput, as_of: date) -> list:
        await asyncio.sleep(1)
        return []


def test_a_search_that_timed_out_with_nothing_fails_the_run(conn, tmp_path) -> None:
    @asynccontextmanager
    async def opened(connection: sqlite3.Connection) -> AsyncIterator[Sources]:
        yield Sources(
            lookup=make_lookup(tmp_path),
            tools={"fixture": Slow()},
            plans=(CollectPlan(section=Section.CLINICAL, tools=("fixture",), timeout_s=0.05),),
        )

    create_run(conn, "R-1", {"asset": "divarasib"}, AS_OF)
    model = FakeLLM(answers())

    result = run_live(conn, "R-1", "divarasib", lambda _: model, opened)

    assert result is None and "clinical incomplete" in last_event(conn).detail
    assert not any(step.startswith("reasoning.") for step, _ in model.calls)
