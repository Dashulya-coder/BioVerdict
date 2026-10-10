"""The synthesis step writes the theses; code keeps only what cites claims and quotes their numbers."""

from pathlib import Path

import pytest

from bioverdict.llm import FakeLLM
from bioverdict.llm.errors import FatalProviderError
from bioverdict.pipeline.reason_score import synthesis_pass
from bioverdict.reasoning.synthesis import (
    MAX_SENTENCES,
    SynthesisDraft,
    figures,
    ground,
    synthesis_prompt,
    write_theses,
)
from bioverdict.scoring.verdict import score_verdict
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import (
    Basis,
    Bundle,
    Claim,
    ClaimType,
    Range,
    Section,
    ThesisKind,
)
from bioverdict.store.runs_repo import create_run, load_events

BUNDLE = Bundle.model_validate_json(
    (Path(__file__).parents[3] / "fixtures/bundles/divarasib.json").read_text()
)


def claim(cid: str, text: str, **kw) -> Claim:
    base = {
        "id": cid,
        "run_id": "R-1",
        "section": Section.CLINICAL,
        "text": text,
        "claim_type": ClaimType.OTHER,
        "basis": Basis.EXTRACTED,
        "confidence": 0.8,
    }
    return Claim(**(base | kw))


CLAIMS = [
    claim("C-1", "Divarasib gave a confirmed response in 53.4% of patients in Phase 1"),
    claim("C-2", "The Phase 3 trial enrolled 1,500 patients with KRAS G12C lung cancer"),
]


def draft(*theses: tuple[str, list[tuple[str, list[str]]]]) -> SynthesisDraft:
    return SynthesisDraft.model_validate(
        {
            "theses": [
                {"kind": kind, "sentences": [{"text": t, "claim_ids": ids} for t, ids in sents]}
                for kind, sents in theses
            ]
        }
    )


def test_a_sentence_that_quotes_its_claims_numbers_is_kept() -> None:
    out = ground(
        draft(("scientific", [("Divarasib answered in 53.4% of patients in Phase 1.", ["C-1"])])),
        CLAIMS,
        "",
    )
    assert [(t.kind, [s.claim_ids for s in t.sentences]) for t in out.theses] == [
        (ThesisKind.SCIENTIFIC, [["C-1"]])
    ]
    assert out.dropped == []


def test_a_number_in_no_cited_claim_and_no_figure_drops_the_sentence() -> None:
    out = ground(
        draft(
            (
                "development_plan",
                [
                    ("The next trial should enrol 800 patients.", ["C-2"]),
                    ("A trial like the last one, with 1500 patients, is needed.", ["C-2"]),
                    ("Response was 53.4%, as the Phase 3 trial showed.", ["C-2"]),  # wrong claim
                ],
            )
        ),
        CLAIMS,
        "",
    )
    kept = [s.text for t in out.theses for s in t.sentences]
    assert kept == ["A trial like the last one, with 1500 patients, is needed."]
    assert len(out.dropped) == 2 and "800" in out.dropped[0] and "53.4" in out.dropped[1]


def test_a_figure_code_computed_may_be_quoted_and_a_phase_is_not_a_number() -> None:
    facts = "- Capital to the next milestone: $101 million (P10 $65 million, P90 $155 million)"
    out = ground(
        draft(
            (
                "investment",
                [
                    (
                        "Reaching the Phase 2/3 readout takes $101 million (P90 $155 million).",
                        ["C-2"],
                    )
                ],
            )
        ),
        CLAIMS,
        facts,
    )
    assert out.dropped == [] and out.theses[0].kind is ThesisKind.INVESTMENT


def test_a_sentence_without_a_claim_of_the_run_is_dropped() -> None:
    out = ground(
        draft(("competitive", [("Two rivals lead.", []), ("Rivals lead.", ["C-99"])])),
        CLAIMS,
        "",
    )
    assert out.theses == [] and len(out.dropped) == 2


def test_theses_come_in_report_order_once_each_and_capped() -> None:
    many = [(f"Sentence {chr(65 + i)}.", ["C-1"]) for i in range(MAX_SENTENCES + 2)]
    out = ground(
        draft(
            ("investment", [("Invest later.", ["C-1"])]),
            ("scientific", many),
            ("scientific", [("A second scientific part.", ["C-1"])]),
        ),
        CLAIMS,
        "",
    )
    assert [t.kind for t in out.theses] == [ThesisKind.SCIENTIFIC, ThesisKind.INVESTMENT]
    assert len(out.theses[0].sentences) == MAX_SENTENCES
    assert any("written twice" in d for d in out.dropped)


def test_the_figures_name_what_was_not_computed_and_that_costs_are_placeholders() -> None:
    result = score_verdict(CLAIMS).model_copy(
        update={
            "capital_to_milestone": Range(p10=65e6, p50=101e6, p90=155e6),
            "months_to_milestone": Range(p10=36, p50=44, p90=53),
        }
    )
    text = figures(result, ["Clinical development: mixed. A rule."], ["rNPV: no market size"])
    assert "$101 million (P10 $65 million, P90 $155 million)" in text
    assert "44 months" in text and "Not computed: rNPV: no market size" in text
    assert "placeholder" in text and "Module answer: Clinical development: mixed" in text


def test_a_long_report_is_cut_to_the_budget_key_claims_first() -> None:
    claims = [claim(f"C-{i}", "x " * 200) for i in range(1, 60)] + [
        claim("C-KEY", "the key claim", critical=True)
    ]
    prompt = synthesis_prompt(BUNDLE, claims, "- Verdict: Conditional", budget=12_000)
    assert len(prompt) < 12_000 and "C-KEY" in prompt and "further claims are not shown" in prompt


def test_the_model_answer_goes_through_code(conn) -> None:
    answer = {
        "theses": [
            {
                "kind": "scientific",
                "sentences": [
                    {"text": "Responses reached 53.4% in Phase 1.", "claim_ids": ["C-1"]}
                ],
            }
        ]
    }
    out = write_theses(
        FakeLLM({"synthesis": answer}), BUNDLE, CLAIMS, score_verdict(CLAIMS), [], []
    )
    assert out.theses[0].sentences[0].text == "Responses reached 53.4% in Phase 1."


class Broken:
    def call(self, step, prompt, schema):
        raise FatalProviderError("refused")


@pytest.fixture
def conn():
    connection = connect(":memory:")
    migrate(connection)
    create_run(connection, "R-1", {"asset": "divarasib"}, BUNDLE.as_of)
    yield connection
    connection.close()


def test_a_failed_synthesis_leaves_the_verdict_and_the_run_says_so(conn) -> None:
    result = score_verdict(CLAIMS)

    after = synthesis_pass(conn, "R-1", BUNDLE, Broken(), CLAIMS, [], result, [])

    assert after == result and after.theses == []
    assert [(e.step, e.status) for e in load_events(conn, "R-1")] == [
        ("synthesis", "started"),
        ("synthesis", "skipped"),
    ]
