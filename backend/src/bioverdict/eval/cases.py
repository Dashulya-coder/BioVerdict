"""The regression cases of docs/eval.md, section 4. The file is written by people (B10)."""

from __future__ import annotations

from datetime import date as date_type
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

from bioverdict.pipeline.live_run import describe_request
from bioverdict.store.models import Verdict


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


_CASES = TypeAdapter(list[EvalCase])


def load_cases(path: Path) -> list[EvalCase]:
    cases = _CASES.validate_python(yaml.safe_load(path.read_text(encoding="utf-8")) or [])
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError(f"{path}: case ids must be unique")
    return cases
