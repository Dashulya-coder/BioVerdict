"""Offline behavior at the connector -> extraction -> frozen bundle boundary."""

import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from bioverdict.agents.collect import CollectPlan, collect
from bioverdict.agents.extraction import (
    ExtractionDraft,
    ground_facts,
    prepare_prompt,
    prioritise,
)
from bioverdict.connectors.fake import FakeConnector
from bioverdict.graph.collect_nodes import CollectNodes
from bioverdict.graph.pipeline import collection_graph
from bioverdict.llm import FakeLLM, LLMClient, LLMConfig, StepConfig
from bioverdict.llm.call_log import SqliteCallLog
from bioverdict.llm.config import HAIKU
from bioverdict.llm.errors import (
    BudgetExceededError,
    ConfigError,
    FatalProviderError,
    RunTimeoutError,
)
from bioverdict.llm.providers.fake import FakeProvider
from bioverdict.store.bundle import compute_content_hash
from bioverdict.store.db import connect
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    EvidenceType,
    Indication,
    ResolverOutput,
    Section,
    SectionStatus,
    SourceKind,
    Target,
)

AS_OF = date(2026, 10, 7)
QUERY = ResolverOutput(indication=Indication(name="NSCLC"), targets=[Target(symbol="KRAS")])
QUOTE = "Response observed in 53.4% of patients."
FACT = {"source_id": "raw-1", "quote": QUOTE, "value": "53.4%"}


def evidence(**overrides) -> Evidence:
    data = {
        "id": "raw-1",
        "source": "fixture",
        "source_family": "publication",
        "source_kind": SourceKind.PEER_REVIEWED,
        "url": "https://example.org/source",
        "excerpt": QUOTE,
        "published_at": date(2026, 7, 2),
        "retrieved_at": datetime(2026, 10, 6, tzinfo=UTC),
        "level": EvidenceLevel.HUMAN_INTERVENTIONAL,
        "independence_group": "lab:one",
        "version": 1,
    }
    return Evidence(**(data | overrides))


def llm(*facts: dict) -> FakeLLM:
    return FakeLLM({"extraction": {"facts": list(facts)}})


async def run(records: list[Evidence], model=None, **limits):
    return await collect(
        [CollectPlan(section=Section.CLINICAL, tools=("fixture",), **limits)],
        {"fixture": FakeConnector(records)},
        model or llm(FACT),
        QUERY,
        AS_OF,
    )


@pytest.mark.parametrize(
    "fact,reason",
    [
        (FACT | {"source_id": "made-up"}, "source id"),
        (FACT | {"quote": "Response observed in 99.9% of patients."}, "verbatim"),
        (FACT | {"value": "99.9%"}, "value"),
        (FACT | {"value": "53"}, "value"),
        (FACT | {"quote": "53.4%", "value": None}, "too short"),
    ],
)
def test_unfetched_ids_quotes_and_values_are_rejected(fact, reason):
    accepted, rejected = ground_facts(ExtractionDraft(facts=[fact]), {"raw-1": evidence()})
    assert accepted == []
    assert reason in rejected[0].reason


@pytest.mark.parametrize(
    "quote,value,accepted",
    [
        ("Change was -53.4%, observed.", "53.4%", False),
        ("Change was -53.4%, observed.", "-53.4%", True),
        ("Measured value was 152 patients.", "52", False),
        ("Measured value was 53.45 percent.", "53.4", False),
        ("Measured value was 53.4, as reported.", "53.4", True),
    ],
)
def test_value_preserves_sign_and_full_number_but_allows_following_punctuation(
    quote, value, accepted
):
    facts, _ = ground_facts(
        ExtractionDraft(facts=[FACT | {"quote": quote, "value": value}]),
        {"raw-1": evidence(excerpt=quote)},
    )
    assert bool(facts) is accepted


def test_model_cannot_write_urls_levels_or_other_provenance():
    with pytest.raises(ValidationError):
        ExtractionDraft(facts=[FACT | {"url": "https://invented.org"}])
    accepted, _ = ground_facts(ExtractionDraft(facts=[FACT]), {"raw-1": evidence()})
    assert accepted[0].evidence == evidence()
    assert accepted[0].value == "53.4%"
    assert (
        ground_facts(
            ExtractionDraft(facts=[FACT]), {"raw-1": evidence(type=EvidenceType.AI_INFERENCE)}
        )[0]
        == []
    )


def test_truncated_text_cannot_be_used_as_grounding_and_status_records_stay_atomic():
    long = evidence(excerpt="x" * 128 + QUOTE)
    _, supplied, truncated = prepare_prompt([long], QUERY, Section.CLINICAL, 128)
    assert truncated and QUOTE not in supplied["raw-1"].excerpt
    assert ground_facts(ExtractionDraft(facts=[FACT]), supplied)[0] == []
    _, supplied, truncated = prepare_prompt(
        [long.model_copy(update={"status_key": "study:status"})], QUERY, Section.CLINICAL, 128
    )
    assert truncated and supplied == {}


async def test_valid_and_invalid_facts_preserve_partial_evidence_and_provenance():
    result = await run([evidence()], llm(FACT, FACT | {"value": "99.9%"}))
    section = result.sections[0]
    assert section.status is SectionStatus.INCOMPLETE and len(section.rejected) == 1
    assert result.evidence == [evidence()]
    assert section.tools_called == ["fixture"] and len(section.calls) == 1
    assert result.statuses[Section.MECHANISM] is SectionStatus.NOT_SEARCHED


async def test_duplicate_facts_are_not_counted_twice_and_ai_inference_is_not_extracted():
    assert (await run([evidence()], llm(FACT, FACT))).evidence == [evidence()]
    result = await run([evidence(type=EvidenceType.AI_INFERENCE)])
    assert not result.evidence and result.sections[0].status is SectionStatus.INCOMPLETE


async def test_no_planned_tools_skips_without_model_calls():
    model = llm()
    result = await collect([CollectPlan(section=Section.CLINICAL)], {}, model, QUERY, AS_OF)
    assert result.statuses[Section.CLINICAL] is SectionStatus.NOT_SEARCHED and not model.calls


@pytest.mark.parametrize(
    "records,facts,status",
    [
        ([], [], SectionStatus.NONE_FOUND),
        ([evidence()], [], SectionStatus.NOT_REPORTED),
        ([evidence()], [FACT], SectionStatus.FOUND),
    ],
)
async def test_empty_source_missing_field_and_found_are_distinct(records, facts, status):
    result = await run(records, llm(*facts))
    assert result.statuses[Section.CLINICAL] is status


async def test_date_filter_runs_before_extraction_including_undated_snapshots():
    model = llm(FACT)
    result = await collect(
        [CollectPlan(section=Section.CLINICAL, tools=("fixture",))],
        {
            "fixture": FakeConnector(
                [
                    evidence(),
                    evidence(id="late", published_at=date(2026, 10, 8)),
                    evidence(
                        id="undated",
                        published_at=None,
                        retrieved_at=datetime(2026, 10, 8, tzinfo=UTC),
                    ),
                ]
            )
        },
        model,
        QUERY,
        AS_OF,
    )
    assert result.evidence == [evidence()]
    assert '"source_id": "late"' not in model.calls[0][1]
    assert '"source_id": "undated"' not in model.calls[0][1]


async def test_latest_status_is_selected_and_its_whole_record_is_kept():
    current = evidence(id="raw-1", status_key="study:status", excerpt=QUOTE + " Other metadata.")
    older = evidence(id="older", status_key="study:status", published_at=date(2025, 1, 1))
    result = await run([older, current])
    assert result.evidence == [current]


class FailingConnector:
    name = "broken"

    async def fetch(self, query, as_of):
        raise OSError("sensitive provider body must not be copied to the trace")


class HangingConnector:
    name = "hanging"

    async def fetch(self, query, as_of):
        await asyncio.Event().wait()
        return []


async def test_source_errors_do_not_stop_other_tools_or_leak_exception_bodies():
    result = await collect(
        [CollectPlan(section=Section.CLINICAL, tools=("broken", "good"))],
        {"broken": FailingConnector(), "good": FakeConnector([evidence()])},
        llm(FACT),
        QUERY,
        AS_OF,
    )
    assert result.evidence == [evidence()]
    assert result.sections[0].status is SectionStatus.INCOMPLETE
    assert result.sections[0].issues == ["broken: OSError"]
    failed = await collect(
        [CollectPlan(section=Section.CLINICAL, tools=("broken",))],
        {"broken": FailingConnector()},
        llm(),
        QUERY,
        AS_OF,
    )
    assert failed.sections[0].status is SectionStatus.ERROR


async def test_step_and_record_limits_do_not_silently_claim_complete_collection():
    model = llm(FACT)
    limited = await collect(
        [CollectPlan(section=Section.CLINICAL, tools=("one", "two"), max_steps=1)],
        {"one": FakeConnector([evidence()]), "two": FakeConnector([evidence()])},
        model,
        QUERY,
        AS_OF,
    )
    assert limited.sections[0].tools_called == ["one"] and len(model.calls) == 1
    assert limited.sections[0].status is SectionStatus.INCOMPLETE
    capped = await run(
        [evidence(), evidence(id="raw-2", url="https://example.org/second")], max_records=1
    )
    assert capped.sections[0].status is SectionStatus.INCOMPLETE


async def test_section_timeout_returns_incomplete_and_next_section_still_runs():
    result = await collect(
        [
            CollectPlan(section=Section.CLINICAL, tools=("hang",), timeout_s=0.01),
            CollectPlan(section=Section.MECHANISM, tools=("good",)),
        ],
        {"hang": HangingConnector(), "good": FakeConnector([evidence()])},
        llm(FACT),
        QUERY,
        AS_OF,
    )
    assert result.statuses[Section.CLINICAL] is SectionStatus.INCOMPLETE
    assert result.statuses[Section.MECHANISM] is SectionStatus.FOUND


class FailedLLM:
    def __init__(self, error):
        self.error, self.calls = error, 0

    def call(self, step, prompt, schema):
        self.calls += 1
        raise self.error


@pytest.mark.parametrize(
    "error,status",
    [
        (BudgetExceededError("cap"), SectionStatus.ERROR),
        (RunTimeoutError("deadline"), SectionStatus.INCOMPLETE),
    ],
)
async def test_budget_or_deadline_stop_skips_sections_without_more_provider_calls(error, status):
    model = FailedLLM(error)
    result = await collect(
        [
            CollectPlan(section=section, tools=("fixture",))
            for section in (Section.CLINICAL, Section.MECHANISM)
        ],
        {"fixture": FakeConnector([evidence()])},
        model,
        QUERY,
        AS_OF,
    )
    assert model.calls == 1
    assert result.statuses[Section.CLINICAL] is status
    assert result.statuses[Section.MECHANISM] is SectionStatus.NOT_SEARCHED


@pytest.mark.parametrize("error", [ConfigError("missing"), FatalProviderError("auth")])
async def test_configuration_and_auth_failures_are_not_hidden_as_empty_sources(error):
    with pytest.raises(type(error)):
        await run([evidence()], FailedLLM(error))


async def test_unknown_or_duplicate_tools_and_sections_fail_before_any_llm_call():
    model = llm()
    for plans in [
        [CollectPlan(section=Section.CLINICAL, tools=("unknown",))],
        [CollectPlan(section=Section.CLINICAL, tools=("fixture", "fixture"))],
        [CollectPlan(section=Section.CLINICAL), CollectPlan(section=Section.CLINICAL)],
    ]:
        with pytest.raises(ValueError):
            await collect(plans, {"fixture": FakeConnector([])}, model, QUERY, AS_OF)
    assert not model.calls


async def test_dag_freezes_canonical_ids_hash_catalog_versions_and_logs_bound_calls(tmp_path: Path):
    path = tmp_path / "collection.db"
    with connect(path) as conn:
        migrate(conn)
        config = LLMConfig(steps={"extraction": StepConfig(models=[HAIKU])})
        model = LLMClient(
            config,
            {"anthropic": FakeProvider(json.dumps({"facts": [FACT]}), name="anthropic")},
            call_log=SqliteCallLog(path),
        ).bind("R-A4")
        graph = collection_graph(
            CollectNodes(
                conn,
                [CollectPlan(section=Section.CLINICAL, tools=("fixture",))],
                {"fixture": FakeConnector([evidence()])},
                model,
            )
        )
        output = await graph.ainvoke({"run_id": "R-A4", "query": QUERY, "as_of": AS_OF})
        bundle = output["bundle"]
        assert bundle.evidence[0].id == "E-0001"
        assert bundle.catalog == ["https://example.org/source"]
        assert bundle.content_hash == compute_content_hash(bundle.evidence, bundle.section_statuses)
        assert load_bundle(conn, "R-A4") == bundle
        replay = await graph.ainvoke({"run_id": "R-A4", "query": QUERY, "as_of": AS_OF})
        assert replay["bundle"].version == 2
        assert replay["bundle"].content_hash == bundle.content_hash
        row = conn.execute("SELECT run_id, step FROM llm_calls LIMIT 1").fetchone()
        assert tuple(row) == ("R-A4", "extraction")
        assert conn.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1


def test_findings_are_read_before_registry_records_and_the_newest_first():
    record = EvidenceLevel.REGISTRY_RECORD
    old = evidence(id="a-old", level=record, published_at=date(2020, 1, 1))
    new = evidence(id="b-new", level=record, published_at=date(2026, 1, 1))
    undated = evidence(id="c-undated", level=record, published_at=None)  # retrieved 2026-10-06
    finding = evidence(id="z-finding", published_at=date(2019, 1, 1))

    order = [item.id for item in prioritise([old, new, undated, finding])]

    assert order == ["z-finding", "c-undated", "b-new", "a-old"]


async def test_a_record_limit_cuts_the_weakest_and_oldest_not_the_highest_id():
    quote = "Response observed in 53.4% of patients."
    registry = evidence(
        id="a-registry", level=EvidenceLevel.REGISTRY_RECORD, url="https://example.org/registry"
    )
    finding = evidence(id="z-finding", excerpt=quote)
    model = llm({"source_id": "z-finding", "quote": quote})

    collected = await run([registry, finding], model, max_records=1)

    (section,) = collected.sections
    assert [fact.evidence.id for fact in section.facts] == ["z-finding"]
    assert section.status is SectionStatus.INCOMPLETE  # something was left unread, and it says so
    assert "a-registry" not in model.calls[0][1]


def test_the_character_budget_is_spent_in_the_order_given():
    first = evidence(id="z-first", excerpt="A" * 100)
    second = evidence(id="a-second", excerpt="B" * 100)

    _, supplied, truncated = prepare_prompt([first, second], QUERY, Section.CLINICAL, 128)

    assert truncated and len(supplied["z-first"].excerpt) == 100
    assert len(supplied["a-second"].excerpt) == 28


async def test_status_facts_reach_the_bundle_whole_without_asking_the_model():
    status = evidence(id="raw-status", status_key="nct:NCT1:overall_status", excerpt='{"a": 1}')
    model = llm()

    collected = await run([status], model)

    (section,) = collected.sections
    assert collected.evidence == [status] and model.calls == []
    assert section.status is SectionStatus.FOUND and section.rejected == []


async def test_the_model_is_asked_about_texts_only_and_cannot_cite_a_status_fact():
    status = evidence(id="raw-status", status_key="nct:NCT1:overall_status", excerpt='{"a": 1}')
    model = llm(FACT, {"source_id": "raw-status", "quote": '{"a": 1}'})

    collected = await run([evidence(), status], model)

    (section,) = collected.sections
    assert "raw-status" not in model.calls[0][1] and "raw-1" in model.calls[0][1]
    assert {e.id for e in collected.evidence} == {"raw-1", "raw-status"}
    assert [r.source_id for r in section.rejected] == ["raw-status"]


async def test_text_that_exceeds_one_prompt_is_read_in_several():
    texts = [
        evidence(id=f"raw-{n}", url=f"https://example.org/{n}", excerpt=f"{n}" * 100)
        for n in range(1, 4)
    ]
    model = llm()

    collected = await run(texts, model, max_chars=128)

    (section,) = collected.sections
    prompts = sorted(prompt for _, prompt in model.calls)
    assert len(prompts) == 3 and all(f'"raw-{n}"' in prompts[n - 1] for n in range(1, 4))
    assert section.status is SectionStatus.NOT_REPORTED  # all of it was read, nothing was found


async def test_text_beyond_the_prompts_allowed_is_left_unread_and_says_so():
    texts = [
        evidence(id=f"raw-{n}", url=f"https://example.org/{n}", excerpt=f"{n}" * 100)
        for n in range(1, 4)
    ]
    model = llm()

    collected = await run(texts, model, max_chars=128, max_batches=2)

    assert len(model.calls) == 2
    assert collected.sections[0].status is SectionStatus.INCOMPLETE


async def test_what_a_connector_could_not_read_makes_the_section_incomplete():
    source = FakeConnector([evidence()], name="fixture")
    source.problems = ["results of NCT1 could not be read (HTTPStatusError)"]

    collected = await collect(
        [CollectPlan(section=Section.CLINICAL, tools=("fixture",))],
        {"fixture": source},
        llm(FACT),
        QUERY,
        AS_OF,
    )

    (section,) = collected.sections
    assert section.facts and section.status is SectionStatus.INCOMPLETE
    assert section.issues == ["fixture: results of NCT1 could not be read (HTTPStatusError)"]
