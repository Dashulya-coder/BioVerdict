"""A deterministic, bounded tool loop. Connectors are injected; no free-form browsing."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict, Field

from bioverdict.agents.extraction import (
    MAX_FACTS,
    ExtractedFact,
    ExtractionDraft,
    RejectedFact,
    ground_facts,
    prepare_prompt,
    prioritise,
)
from bioverdict.contracts import LLM, Connector
from bioverdict.llm.errors import (
    BudgetExceededError,
    ConfigError,
    FatalProviderError,
    LLMError,
    RunTimeoutError,
)
from bioverdict.reasoning.prompts import RETRY_RESERVE
from bioverdict.store.bundle import select_bundle_evidence
from bioverdict.store.models import (
    Evidence,
    EvidenceType,
    LLMResult,
    ResolverOutput,
    Section,
    SectionStatus,
)


class CollectPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    section: Section
    tools: tuple[str, ...] = ()
    max_steps: int = Field(default=8, ge=1, le=8)
    timeout_s: float = Field(default=90, gt=0, le=90, allow_inf_nan=False)
    max_records: int = Field(default=50, ge=1, le=50)
    max_chars: int = Field(default=24_000, ge=128, le=24_000)  # of text per extraction prompt
    max_batches: int = Field(default=3, ge=1, le=4)  # extraction prompts per source


@dataclass
class SectionCollection:
    section: Section
    status: SectionStatus = SectionStatus.NOT_SEARCHED
    facts: list[ExtractedFact] = field(default_factory=list)
    rejected: list[RejectedFact] = field(default_factory=list)
    calls: list[LLMResult] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    halted: bool = False


@dataclass
class Collection:
    sections: list[SectionCollection]

    @property
    def evidence(self) -> list[Evidence]:
        return [fact.evidence for section in self.sections for fact in section.facts]

    @property
    def statuses(self) -> dict[Section, SectionStatus]:
        statuses = dict.fromkeys(Section, SectionStatus.NOT_SEARCHED)
        statuses.update({section.section: section.status for section in self.sections})
        return statuses


def _split(records: list[Evidence]) -> tuple[list[Evidence], list[Evidence]]:
    """Status facts, which are kept whole, and the records a model picks quotes from.

    A status record (a trial's status or design, a database snapshot) is one fact: extraction
    never cuts it, so asking a model about it could only lose it. It goes to the bundle as
    retrieved, which costs nothing and leaves the model's fact limit for the texts.
    """
    whole = [r for r in records if r.status_key and r.type is EvidenceType.SOURCE_FACT]
    kept = {record.id for record in whole}
    return whole, [record for record in records if record.id not in kept]


def _fit(
    records: list[Evidence], query: ResolverOutput, plan: CollectPlan, limit: int | None
) -> tuple[str, dict[str, Evidence]]:
    """One prompt of up to `plan.max_chars` of text that also fits what the endpoint accepts.

    The limit counts the whole request, so the text allowance is lowered by however much the
    prompt (instructions, JSON framing, escaping) is over the room left for a retry.
    """
    # Start from the text the prompt can really hold: lowering a bigger allowance cuts nothing.
    room = min(plan.max_chars, sum(len(record.excerpt) for record in records))
    for _ in range(8):
        prompt, supplied, _ = prepare_prompt(records, query, plan.section, room, whole_records=True)
        over = 0 if limit is None else len(prompt) + RETRY_RESERVE - limit
        if over <= 0 or room <= 128:
            return prompt, supplied
        room = max(128, room - over - 64)
    return prompt, supplied


async def _extract(
    llm: LLM,
    records: list[Evidence],
    query: ResolverOutput,
    plan: CollectPlan,
    out: SectionCollection,
) -> bool:
    """Ask the model for quotes from `records`, in up to `max_batches` prompts sent together.

    Each prompt holds up to `max_chars` of text and may return up to 32 facts. Returns whether
    anything was left unread or cut, so that the section is not called complete.
    """
    if len({record.id for record in records}) != len(records):
        raise ValueError("connector returned ambiguous source ids")
    budget_of = getattr(llm, "input_budget", None)
    limit = budget_of("extraction", ExtractionDraft) if callable(budget_of) else None
    batches: list[tuple[str, dict[str, Evidence]]] = []
    remaining, cut = records, False
    while remaining and len(batches) < plan.max_batches:
        prompt, supplied = _fit(remaining, query, plan, limit)
        if not supplied:
            break
        full = {record.id: len(record.excerpt) for record in remaining}
        cut |= any(len(item.excerpt) < full[key] for key, item in supplied.items())
        batches.append((prompt, supplied))
        remaining = [record for record in remaining if record.id not in supplied]

    results = await asyncio.gather(
        *(
            asyncio.to_thread(llm.call, "extraction", prompt, ExtractionDraft)
            for prompt, _ in batches
        )
    )
    incomplete = cut or bool(remaining)
    for result, (_, supplied) in zip(results, batches, strict=True):
        out.calls.append(result)
        draft = ExtractionDraft.model_validate(result.parsed)
        facts, rejected = ground_facts(draft, supplied)
        out.facts.extend(facts)
        out.rejected.extend(rejected)
        incomplete |= bool(rejected) or len(draft.facts) == MAX_FACTS
    return incomplete


async def _collect_section(
    plan: CollectPlan,
    tools: Mapping[str, Connector],
    llm: LLM,
    query: ResolverOutput,
    as_of: date,
) -> SectionCollection:
    out = SectionCollection(plan.section)
    completed = 0
    incomplete = False
    try:
        async with asyncio.timeout(plan.timeout_s):
            for name in plan.tools[: plan.max_steps]:
                out.tools_called.append(name)
                try:
                    records = prioritise(
                        select_bundle_evidence(await tools[name].fetch(query, as_of), as_of)
                    )
                    # A connector may read most of a source and name what it could not read
                    # (`problems`). That is a partial answer, never a complete one.
                    unread = [
                        f"{name}: {problem}" for problem in getattr(tools[name], "problems", [])
                    ]
                    out.issues += unread
                    incomplete |= bool(unread)
                    if not records:
                        completed += 1
                        continue
                    # The record limit holds for each kind: status facts cost no model call.
                    whole, text = _split(records)
                    incomplete |= max(len(whole), len(text)) > plan.max_records
                    whole, text = whole[: plan.max_records], text[: plan.max_records]
                    out.facts.extend(ExtractedFact(record, None) for record in whole)
                    incomplete |= await _extract(llm, text, query, plan, out)
                    completed += 1
                except ConfigError, FatalProviderError:
                    raise
                except (BudgetExceededError, RunTimeoutError) as exc:
                    out.issues.append(f"{name}: {type(exc).__name__}")
                    out.halted = True
                    incomplete |= isinstance(exc, RunTimeoutError)
                    break
                except (LLMError, httpx.HTTPError, OSError, ValueError, KeyError) as exc:
                    # Provider exception text can contain credentials or response bodies.
                    out.issues.append(f"{name}: {type(exc).__name__}")
    except TimeoutError:
        out.issues.append("section deadline exceeded")
        incomplete = True
    if not plan.tools:
        return out
    if incomplete or len(plan.tools) > plan.max_steps:
        out.status = SectionStatus.INCOMPLETE
    elif out.issues:
        out.status = SectionStatus.INCOMPLETE if completed else SectionStatus.ERROR
    elif out.facts:
        out.status = SectionStatus.FOUND
    else:
        out.status = SectionStatus.NOT_REPORTED if out.calls else SectionStatus.NONE_FOUND
    return out


async def collect(
    plans: Sequence[CollectPlan],
    tools: Mapping[str, Connector],
    llm: LLM,
    query: ResolverOutput,
    as_of: date,
) -> Collection:
    """Preflight the allowlist; stop scheduling calls after a global budget/deadline failure."""
    sections = [plan.section for plan in plans]
    if len(sections) != len(set(sections)):
        raise ValueError("each section may be planned only once")
    for plan in plans:
        if len(plan.tools) != len(set(plan.tools)):
            raise ValueError("a tool may be called only once per section")
        if set(plan.tools) - tools.keys():
            raise ValueError("collection plan names an unavailable tool")
    results: list[SectionCollection] = []
    halted = False
    for plan in plans:
        if halted:
            result = SectionCollection(plan.section, issues=["skipped after budget/deadline stop"])
        else:
            result = await _collect_section(plan, tools, llm, query, as_of)
        results.append(result)
        halted |= result.halted
    return Collection(results)
