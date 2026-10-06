"""Function contracts between the two tracks (docs/work-plan.md, section 3).

Changes need both owners' approval. Fakes in tests must satisfy these protocols.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from bioverdict.store.models import (
    Bundle,
    Claim,
    ClaimEvidenceLink,
    Evidence,
    LLMResult,
    ResolverOutput,
    VerdictResult,
    VerificationReport,
)


@runtime_checkable
class Connector(Protocol):
    """Track A. One data source; returns Evidence, never free text."""

    name: str

    def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]: ...


@runtime_checkable
class LLM(Protocol):
    """Track B. The only way code talks to a model; validates output against `schema`."""

    def call(self, step: str, prompt: str, schema: type[BaseModel]) -> LLMResult: ...


@runtime_checkable
class Reasoner(Protocol):
    """Track B. Runs with no network access: only the frozen bundle exists."""

    def reason(self, bundle: Bundle) -> tuple[list[Claim], list[ClaimEvidenceLink]]: ...


@runtime_checkable
class Scorer(Protocol):
    """Track B. Deterministic code: same claims in, same verdict out."""

    def score(self, claims: list[Claim], links: list[ClaimEvidenceLink]) -> VerdictResult: ...


@runtime_checkable
class Verifier(Protocol):
    """Track B. Grounding and entailment checks before a report is released."""

    def verify(
        self, claims: list[Claim], links: list[ClaimEvidenceLink], bundle: Bundle
    ) -> VerificationReport: ...
