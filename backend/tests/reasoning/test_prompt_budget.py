"""A prompt must fit what the endpoint accepts, and say what it left out."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from bioverdict.llm import LLMClient, LLMConfig
from bioverdict.llm.providers.fake import FakeProvider
from bioverdict.llm.providers.openai import OpenAIProvider
from bioverdict.reasoning import ALL_MODULES, CLINICAL, MECHANISM, ModuleReasoner
from bioverdict.reasoning.prompts import (
    DEFAULT_EXCERPT_CAP,
    RETRY_RESERVE,
    boundary_tag,
    build_prompt,
    build_prompts,
)
from bioverdict.reasoning.schemas import ModuleDraft
from bioverdict.store.models import Bundle, Evidence, EvidenceLevel, SourceKind

BASE = Bundle.model_validate_json(
    (Path(__file__).parents[3] / "fixtures/bundles/divarasib.json").read_text()
)
FAMILIES = ("registry", "literature", "target_database", "cms_spending", "cdc_indicator")
LEVELS = list(EvidenceLevel)


def item(i: int, family: str, chars: int = 500, level: EvidenceLevel | None = None) -> Evidence:
    return Evidence(
        id=f"E-{i:04d}",
        source=f"source {family}",
        source_family=family,
        source_kind=SourceKind.REGISTRY if family == "registry" else SourceKind.PEER_REVIEWED,
        url=f"https://example.org/{i}",
        excerpt=(f"item {i} about {family}. " * 60)[:chars],
        published_at=date(2025, 1, 1 + i % 28),
        retrieved_at=datetime(2026, 10, 9, tzinfo=UTC),
        level=level or LEVELS[i % len(LEVELS)],
        independence_group=f"group:{i % 9}",
        version=1,
    )


def big_bundle(n: int = 100, chars: int = 500) -> Bundle:
    evidence = [item(i, FAMILIES[i % len(FAMILIES)], chars) for i in range(1, n + 1)]
    return BASE.model_copy(update={"evidence": evidence})


# --- sizing -------------------------------------------------------------------------------------


@pytest.mark.parametrize("budget", [4000, 8000, 13000])
def test_the_prompt_fits_the_budget_and_keeps_the_retry_reserve(budget: int) -> None:
    built = build_prompt(MECHANISM.instruction, big_bundle(), budget=budget)
    assert len(built.text) + RETRY_RESERVE <= budget


def test_a_cut_keeps_the_strongest_evidence_and_names_what_it_left_out() -> None:
    bundle = big_bundle()
    built = build_prompt(CLINICAL.instruction, bundle, budget=8000, families=CLINICAL.families)
    pool = [e for e in bundle.evidence if e.source_family in CLINICAL.families]
    assert built.omitted and len(built.omitted) < len(pool)
    shown = [e for e in pool if e.id not in built.omitted]
    strongest = min(pool, key=lambda e: (LEVELS.index(e.level), e.id))
    assert strongest.id not in built.omitted
    assert all(LEVELS.index(s.level) <= LEVELS.index(LEVELS[-2]) for s in shown[:3])
    assert f"{len(built.omitted)} further evidence items" in built.text
    assert all(f'id="{e.id}"' in built.text for e in shown)


def test_without_a_budget_nothing_changes_for_a_small_bundle() -> None:
    plain = build_prompt(MECHANISM.instruction, BASE)
    assert plain.omitted == [] and all(e.excerpt in plain.text for e in BASE.evidence)


def test_a_long_excerpt_is_shown_by_its_beginning_only_when_characters_are_scarce() -> None:
    bundle = BASE.model_copy(update={"evidence": [item(1, "literature", chars=3000)]})
    scarce = build_prompt(MECHANISM.instruction, bundle, budget=9000)
    assert "more characters not shown" in scarce.text
    assert bundle.evidence[0].excerpt[:DEFAULT_EXCERPT_CAP] in scarce.text
    assert bundle.evidence[0].excerpt not in scarce.text


def test_the_evidence_header_is_compact() -> None:
    e = item(7, "literature", chars=100)
    bundle = BASE.model_copy(update={"evidence": [e]})
    tag = boundary_tag(bundle)
    text = build_prompt("task", bundle).text
    block = text[text.index(f"<{tag} id=") : text.index(f"</{tag}>") + len(tag) + 3]
    assert len(block) - len(e.excerpt) < 140  # it was about 180 before


# --- what each module reads ----------------------------------------------------------------------


def test_no_module_reads_market_records() -> None:
    market = {
        "approved_analog",
        "cdc_indicator",
        "cms_spending",
        "cancer_incidence",
        "population",
        "orphanet_prevalence",
    }
    for module in ALL_MODULES:
        assert module.families is not None and not (module.families & market), module.name


def test_a_module_prompt_holds_only_its_families() -> None:
    built = build_prompt(MECHANISM.instruction, big_bundle(), families=MECHANISM.families)
    assert "source registry" not in built.text and "source cms_spending" not in built.text
    assert "source literature" in built.text and "source target_database" in built.text


@pytest.mark.parametrize("module", ALL_MODULES, ids=lambda m: m.name)
@pytest.mark.parametrize("budget", [None, 13000])
def test_full_recompute_shows_analyst_additions_to_every_module(module, budget) -> None:
    new = item(999, "analyst_added", chars=100)
    market = item(998, "cms_spending", chars=100)
    bundle = BASE.model_copy(update={"evidence": [new, market]})
    prompts = build_prompts(
        module.instruction, bundle, budget=budget, families=module.families, max_batches=3
    )
    assert any(new.excerpt in p.text for p in prompts)
    assert all(market.excerpt not in p.text for p in prompts)


# --- through the client: every request fits ------------------------------------------------------


class GatewayLike(FakeProvider):
    """Counts characters the way the gateway adapter does."""

    input_chars = OpenAIProvider(client=object()).input_chars


def test_every_module_call_fits_the_batch_size_for_a_large_bundle() -> None:
    from bioverdict.llm.config import GATEWAY_BATCH_CHARS, GATEWAY_CLINICAL_CHARS

    provider = GatewayLike('{"claims": []}', name="openai")
    config = LLMConfig.for_provider("openai")
    client = LLMClient(config, {"openai": provider})
    ModuleReasoner(client.bind("R-1"), "R-1").reason(big_bundle(150, 800))
    assert len(ALL_MODULES) <= len(provider.requests) <= 4 * len(ALL_MODULES)
    for request in provider.requests:
        # No endpoint limit: the step's own size, kept so that the answer fits the output limit.
        size = (
            GATEWAY_CLINICAL_CHARS
            if "Clinical development" in request.prompt
            else GATEWAY_BATCH_CHARS
        )
        assert provider.input_chars(request) + RETRY_RESERVE <= size
    assert ModuleDraft  # the schema the budget was computed for


def test_a_small_bundle_is_not_trimmed_on_the_gateway() -> None:
    provider = GatewayLike('{"claims": []}', name="openai")
    client = LLMClient(LLMConfig.for_provider("openai"), {"openai": provider})
    reasoner = ModuleReasoner(client.bind("R-1"), "R-1")
    reasoner.reason(BASE)
    assert reasoner.trace.omitted_evidence == []
