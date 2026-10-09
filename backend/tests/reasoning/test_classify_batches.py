from bioverdict.reasoning.classify_evidence import build_prompts
from bioverdict.reasoning.prompts import RETRY_RESERVE
from bioverdict.store.models import Basis, Claim, Section

from .test_prompt_budget import big_bundle


def _claims(n: int) -> list[Claim]:
    return [
        Claim(
            id=f"C-{i:04d}",
            run_id="R-1",
            section=Section.MECHANISM,
            text="x" * 400,
            basis=Basis.INFERRED,
            confidence=0.5,
        )
        for i in range(1, n + 1)
    ]


def test_new_evidence_is_split_into_prompts_that_fit() -> None:
    bundle = big_bundle(60, 800)
    prompts, unread = build_prompts(_claims(10), bundle.evidence, bundle, budget=12_000)
    assert len(prompts) > 1
    for text, shown in prompts:
        assert len(text) + RETRY_RESERVE <= 12_000 + 1
        assert all(e.id in text for e in shown)
    ids = [e.id for _, shown in prompts for e in shown]
    assert len(ids) == len(set(ids))
    assert set(ids) | set(unread) == {e.id for e in bundle.evidence}


def test_without_a_budget_one_prompt_carries_everything() -> None:
    bundle = big_bundle(5, 100)
    prompts, unread = build_prompts(_claims(2), bundle.evidence, bundle, budget=None)
    assert len(prompts) == 1 and unread == []
