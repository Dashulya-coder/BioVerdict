from datetime import UTC, date, datetime

from bioverdict.market.tam import MarketEstimate
from bioverdict.scoring import financials
from bioverdict.scoring.financials import (
    ANY_INDICATION,
    IN_INDICATION,
    financial_model,
    read_stage,
)
from bioverdict.store.models import (
    Bundle,
    Evidence,
    EvidenceLevel,
    Range,
    SourceKind,
    TamEstimate,
)


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
    assert read_stage(bundle) == ("phase3", ["E-0002"], ANY_INDICATION)


def test_the_stage_in_the_indication_wins_over_the_highest_stage_elsewhere() -> None:
    bundle = _bundle(
        '{"maximumClinicalStage": "PHASE_3", "indication": {"maxClinicalStage": "PHASE_1"}}'
    )
    assert read_stage(bundle) == ("phase1", ["E-0001"], IN_INDICATION)


def test_an_asset_approved_in_the_indication_has_no_phase_left_to_model() -> None:
    bundle = _bundle(
        '{"maximumClinicalStage": "PHASE_3", "indication": {"maxClinicalStage": "APPROVAL"}}'
    )
    assert read_stage(bundle)[0] is None


def test_an_unknown_stage_in_the_indication_falls_back_to_the_highest_stage() -> None:
    bundle = _bundle(
        '{"maximumClinicalStage": "PHASE_2", "indication": {"maxClinicalStage": "UNKNOWN"}}'
    )
    assert read_stage(bundle) == ("phase2", ["E-0001"], ANY_INDICATION)


def _market(patients: float, monkeypatch) -> None:
    people = Range(p10=patients * 0.9, p50=patients, p90=patients * 1.1)
    price = Range(p10=60_000, p50=80_000, p90=100_000)
    size = Range(p10=people.p10 * price.p10, p50=people.p50 * price.p50, p90=people.p90 * price.p90)
    tam = TamEstimate(addressable_patients=people, annual_price_usd=price, tam_usd=size)
    monkeypatch.setattr(financials, "estimate_market", lambda bundle: MarketEstimate(tam=tam))


def test_a_market_that_is_a_ceiling_gives_no_rnpv_and_says_why(monkeypatch) -> None:
    _market(90_000_000, monkeypatch)  # everyone with a common condition
    fin = financial_model(_bundle('"maximumClinicalStage": "PHASE_3"'), "obesity disorder")
    assert fin.pos is not None and fin.rnpv is None
    assert "ceiling" in fin.missing[0]


def test_a_plausible_market_gives_an_rnpv(monkeypatch) -> None:
    _market(28_000, monkeypatch)
    fin = financial_model(_bundle('"maximumClinicalStage": "PHASE_3"'), "lung cancer")
    assert fin.rnpv is not None and fin.rnpv.rnpv.p50 > 0 and not fin.missing


def test_without_a_stage_nothing_is_computed_and_it_says_so() -> None:
    fin = financial_model(_bundle("no stage here"), "NSCLC")
    assert fin.pos is None and fin.rnpv is None and "stage" in fin.missing[0]


def test_a_stage_without_a_market_gives_pos_but_no_rnpv() -> None:
    fin = financial_model(
        _bundle('"maximumClinicalStage": "PHASE_2"'), "non-small cell lung cancer"
    )
    assert fin.area == "oncology" and fin.pos is not None
    assert fin.rnpv is None and "market" in fin.missing[0]


def test_with_financials_fills_the_verdict_and_k5_is_held_back_as_a_near_miss() -> None:
    from bioverdict.scoring.financials import Financials, with_financials
    from bioverdict.scoring.pos import probability_of_success
    from bioverdict.scoring.rnpv import run_rnpv
    from bioverdict.scoring.verdict import score_verdict

    pos = probability_of_success("phase3", "oncology")
    rnpv = run_rnpv(pos, "phase3", Range(p10=1, p50=2, p90=3), Range(p10=1e5, p50=1.5e5, p90=2e5))
    fin = Financials(stage="phase3", area="oncology", pos=pos, rnpv=rnpv)
    result = with_financials(score_verdict([], rnpv.rnpv), fin)
    assert result.rnpv == rnpv.rnpv and result.capital == rnpv.capital
    assert result.pos == pos.pos
    k5 = next(g for g in result.gates if g.gate_id.value == "K5")
    assert not k5.fired and k5.near_miss is not None
