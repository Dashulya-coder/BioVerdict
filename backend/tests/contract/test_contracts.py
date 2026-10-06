"""Trivial fakes must satisfy each protocol; Phase 0 gives every real implementation a target."""

from datetime import date

from pydantic import BaseModel

from bioverdict.contracts import LLM, Connector, Reasoner, Scorer, Verifier
from bioverdict.store.models import (
    Bundle,
    Claim,
    ClaimEvidenceLink,
    Evidence,
    LLMResult,
    ResolverOutput,
    Verdict,
    VerdictResult,
    VerificationReport,
)


class FakeConnector:
    name = "fake"

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        return []


class FakeLLM:
    def call(self, step: str, prompt: str, schema: type[BaseModel]) -> LLMResult:
        return LLMResult(step=step, provider="fake", model="fake")


class FakeReasoner:
    def reason(self, bundle: Bundle) -> tuple[list[Claim], list[ClaimEvidenceLink]]:
        return [], []


class FakeScorer:
    def score(self, claims: list[Claim], links: list[ClaimEvidenceLink]) -> VerdictResult:
        return VerdictResult(verdict=Verdict.CONDITIONAL, confidence=0.5)


class FakeVerifier:
    def verify(
        self, claims: list[Claim], links: list[ClaimEvidenceLink], bundle: Bundle
    ) -> VerificationReport:
        return VerificationReport()


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeConnector(), Connector)
    assert isinstance(FakeLLM(), LLM)
    assert isinstance(FakeReasoner(), Reasoner)
    assert isinstance(FakeScorer(), Scorer)
    assert isinstance(FakeVerifier(), Verifier)


def test_object_without_method_is_rejected() -> None:
    assert not isinstance(object(), Scorer)
