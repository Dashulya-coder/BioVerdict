"""The regression cases of docs/eval.md, section 4. The file is written by people (B10)."""

from __future__ import annotations

from datetime import date as date_type
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from bioverdict.pipeline.live_run import describe_request
from bioverdict.store.models import EvidenceLevel, SourceKind, Verdict

# Which collection a case belongs to. `demo` is the pair shown on stage, `regression` holds
# expert-style expectations, `backtest` is a retrospective case whose `outcome` is known, and
# `smoke` only proves that the runner runs.
CaseSet = Literal["demo", "regression", "backtest", "smoke"]


class CaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str | None = None
    indication: str | None = None
    mechanism: str | None = None
    query: str | None = None  # free text, live runs only

    @model_validator(mode="after")
    def _says_something(self) -> CaseInput:
        if not self.text():
            raise ValueError("give an asset, an indication with a mechanism, or a query")
        return self

    def text(self) -> str:
        """The one line a run is started with."""
        typed = (self.query or "").strip()
        return typed or describe_request(self.asset, self.indication, self.mechanism)


class Signal(BaseModel):
    """A public event the expectation rests on. A noisy proxy for an expert's verdict."""

    model_config = ConfigDict(extra="forbid")

    text: str
    url: str | None = None
    date: date_type | str | None = None  # YAML reads a bare date as a date


class Outcome(BaseModel):
    """What happened after `as_of`, for a retrospective case. It is never shown to the model: the
    report puts it beside the verdict and the risks so that a person can judge the argument."""

    model_config = ConfigDict(extra="forbid")

    text: str
    url: str | None = None
    date: date_type | str | None = None


class ProbeEvidence(BaseModel):
    """A real document, copied verbatim, that is added to a finished run to see what moves."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=20, max_length=6000)
    url: str = Field(pattern=r"^https?://")
    source: str = Field(min_length=1, max_length=200)
    source_kind: SourceKind
    level: EvidenceLevel
    published_at: date_type | None = None


class Probe(BaseModel):
    """A sensitivity test (docs/eval.md, section 3): add one document and check, by code, that the
    run moved as much as that kind of document should move it.

    - `strong`: a decisive result. The verdict, or a key claim's confidence, moves in `direction`.
    - `weak`: a minor result. Some confidence moves in `direction`, the verdict does not change.
    - `noise`: an irrelevant document. Nothing moves.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["strong", "weak", "noise"]
    direction: Literal["lower", "higher"] | None = None
    evidence: ProbeEvidence
    as_of: date_type | None = None  # cutoff of the recomputed run; default: the case's
    note: str = ""

    @model_validator(mode="after")
    def _direction_matches_kind(self) -> Probe:
        if self.kind == "noise" and self.direction is not None:
            raise ValueError("a noise probe moves nothing, so it has no direction")
        if self.kind != "noise" and self.direction is None:
            raise ValueError(f"a {self.kind} probe needs a direction (lower or higher)")
        return self


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Za-z0-9._-]+$")
    input: CaseInput
    as_of: date_type | None = None  # default: the day the case is run
    expected_verdict: list[Verdict] = []  # any of these counts; empty means no expectation
    expected_top_risks: list[str] = []
    signals: list[Signal] = []
    recorded_by: str | None = None
    recorded_at: date_type | str | None = None
    set: CaseSet = "regression"
    outcome: Outcome | None = None  # backtests: what happened next
    probes: list[Probe] = []  # sensitivity tests, run on the first finished run of the case


_CASES = TypeAdapter(list[EvalCase])


def load_cases(path: Path) -> list[EvalCase]:
    cases = _CASES.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: case ids must be unique")
    return cases
