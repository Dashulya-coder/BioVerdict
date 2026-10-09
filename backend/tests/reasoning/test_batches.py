from bioverdict.reasoning.modules import ALL_MODULES, MECHANISM
from bioverdict.reasoning.prompts import RETRY_RESERVE, build_prompts
from bioverdict.reasoning.schemas import DraftClaim, ModuleDraft, merge_drafts

from .test_prompt_budget import big_bundle


def _ids(text: str) -> set[str]:
    return {w for w in text.replace("[", " ").replace("]", " ").split() if w.startswith("E-")}


def test_a_large_bundle_is_read_in_several_batches_that_do_not_overlap() -> None:
    bundle = big_bundle(150, 800)
    prompts = build_prompts(
        MECHANISM.instruction, bundle, budget=12_000, families=MECHANISM.families, max_batches=3
    )
    assert 1 < len(prompts) <= 3
    for prompt in prompts:
        assert len(prompt.text) + RETRY_RESERVE <= 12_000 + 1
    seen = [_ids(p.text) for p in prompts]
    assert not (seen[0] & seen[1])
    assert "batch 1 of the evidence" in prompts[0].text
    assert "Do not write `unknown`" in prompts[0].text


def test_a_bundle_that_fits_is_one_plain_prompt() -> None:
    prompts = build_prompts(
        MECHANISM.instruction,
        big_bundle(3, 100),
        budget=15_000,
        families=MECHANISM.families,
        max_batches=3,
    )
    assert len(prompts) == 1 and "batch" not in prompts[0].text.split("## Your task")[0]


def test_no_budget_means_one_prompt() -> None:
    assert len(build_prompts("x", big_bundle(150, 800), budget=None, max_batches=3)) == 1
    assert len(ALL_MODULES) > 0


def _claim(text: str, basis: str = "extracted", gates: list | None = None, critical=False):
    return DraftClaim.model_validate(
        {
            "text": text,
            "basis": basis,
            "claim_type": "other",
            "links": [],
            "gate_signals": gates or [],
            "critical": critical,
        }
    )


def test_merge_unites_the_same_claim_and_drops_unknown() -> None:
    a = ModuleDraft(claims=[_claim("KRAS G12C drives tumours"), _claim("Gap", "unknown")])
    b = ModuleDraft(claims=[_claim("kras  g12c drives tumours", critical=True), _claim("Other")])
    merged = merge_drafts([a, b], drop_unknown=True)
    assert [c.text for c in merged.claims] == ["KRAS G12C drives tumours", "Other"]
    assert merged.claims[0].critical is True
    assert len(merge_drafts([a], drop_unknown=False).claims) == 2
