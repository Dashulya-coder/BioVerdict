"""A deterministic, bounded tool loop. Connectors are injected; no free-form browsing."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import httpx
from pydantic import BaseModel, ConfigDict, Field

from bioverdict.agents.extraction import (
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
from bioverdict.store.bundle import select_bundle_evidence
from bioverdict.store.models import Evidence, LLMResult, ResolverOutput, Section, SectionStatus


class CollectPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    section: Section
    tools: tuple[str, ...] = ()
    max_steps: int = Field(default=8, ge=1, le=8)
    timeout_s: float = Field(default=90, gt=0, le=90, allow_inf_nan=False)
    max_records: int = Field(default=50, ge=1, le=50)
    max_chars: int = Field(default=24_000, ge=128, le=24_000)


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
                    if not records:
                        completed += 1
                        continue
                    incomplete |= len(records) > plan.max_records
                    prompt, supplied, truncated = prepare_prompt(
                        records[: plan.max_records], query, plan.section, plan.max_chars
                    )
                    incomplete |= truncated
                    if not supplied:
                        completed += 1
                        continue
                    result = await asyncio.to_thread(
                        llm.call, "extraction", prompt, ExtractionDraft
                    )
                    out.calls.append(result)
                    draft = ExtractionDraft.model_validate(result.parsed)
                    facts, rejected = ground_facts(draft, supplied)
                    out.facts.extend(facts)
                    out.rejected.extend(rejected)
                    incomplete |= bool(rejected) or len(draft.facts) == 32
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
