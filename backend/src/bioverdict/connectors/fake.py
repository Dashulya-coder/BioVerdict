"""Connector that serves evidence from memory or a fixture bundle, with no network."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import Bundle, Evidence, ResolverOutput


class FakeConnector:
    """Satisfies `Connector`. Applies the same `as_of` rule real connectors must apply."""

    def __init__(self, evidence: list[Evidence], name: str = "fake") -> None:
        self.name = name
        self._evidence = list(evidence)

    @classmethod
    def from_bundle_file(cls, path: Path, name: str = "fake") -> FakeConnector:
        bundle = Bundle.model_validate_json(path.read_text(encoding="utf-8"))
        return cls(bundle.evidence, name=name)

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        # `query` is ignored on purpose: a fixture is one fixed asset.
        return filter_as_of(self._evidence, as_of)
