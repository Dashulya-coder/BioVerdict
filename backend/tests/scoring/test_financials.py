from datetime import UTC, date, datetime

from bioverdict.scoring.financials import financial_model, read_stage
from bioverdict.store.models import Bundle, Evidence, EvidenceLevel, SourceKind


def _bundle(*excerpts: str) -> Bundle:
    evidence = [
        Evidence(
            id=f"E-{i:04d}",
            source="fixture",
            source_family="target_database",
            source_kind=SourceKind.REGISTRY,
            url="https://example.org",
            excerpt=text,
            published_at=date(2026, 1, 1),
            retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
            level=EvidenceLevel.REGISTRY_RECORD,
            independence_group="db",
            version=1,
        )
        for i, text in enumerate(excerpts, 1)
    ]
    return Bundle(
        bundle_id="B-1",
        run_id="R-1",
        version=1,
        as_of=date(2026, 10, 7),
        content_hash="sha256:x",
        catalog=[],
        evidence=evidence,
        section_statuses={},
        created_at=datetime(2026, 10, 7, tzinfo=UTC),
    )


def test_stage_is_the_highest_reported_phase() -> None:
    bundle = _bundle('"maximumClinicalStage": "PHASE_1"', '"maximumClinicalStage": "PHASE_3"')
    assert read_stage(bundle) == ("phase3", ["E-0002"])


def test_without_a_stage_nothing_is_computed_and_it_says_so() -> None:
    fin = financial_model(_bundle("no stage here"), "NSCLC")
    assert fin.pos is None and fin.rnpv is None and "stage" in fin.missing[0]


def test_a_stage_without_a_market_gives_pos_but_no_rnpv() -> None:
    fin = financial_model(
        _bundle('"maximumClinicalStage": "PHASE_2"'), "non-small cell lung cancer"
    )
    assert fin.area == "oncology" and fin.pos is not None
    assert fin.rnpv is None and "market" in fin.missing[0]


def test_with_financials_fills_the_verdict_and_k5_can_fire() -> None:
    from bioverdict.scoring.financials import Financials, with_financials
    from bioverdict.scoring.pos import probability_of_success
    from bioverdict.scoring.rnpv import run_rnpv
    from bioverdict.scoring.verdict import score_verdict
    from bioverdict.store.models import Range

    pos = probability_of_success("phase3", "oncology")
    rnpv = run_rnpv(pos, "phase3", Range(p10=1, p50=2, p90=3), Range(p10=1e5, p50=1.5e5, p90=2e5))
    fin = Financials(stage="phase3", area="oncology", pos=pos, rnpv=rnpv)
    result = with_financials(score_verdict([], rnpv.rnpv), fin)
    assert result.rnpv == rnpv.rnpv and result.capital == rnpv.capital
    assert result.pos == pos.pos
    assert any(g.gate_id.value == "K5" and g.fired for g in result.gates)
