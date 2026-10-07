"""Collect and freeze boundaries; no dependency on the pending API/CLI PRs."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import date
from typing import NotRequired, TypedDict

from bioverdict.agents.collect import Collection, CollectPlan, collect
from bioverdict.contracts import LLM, Connector
from bioverdict.store.freeze import freeze
from bioverdict.store.models import Bundle, ResolverOutput


class CollectState(TypedDict):
    run_id: str
    query: ResolverOutput
    as_of: date
    collection: NotRequired[Collection]
    bundle: NotRequired[Bundle]


class CollectNodes:
    def __init__(
        self,
        conn: sqlite3.Connection,
        plans: Sequence[CollectPlan],
        tools: Mapping[str, Connector],
        llm: LLM,
    ) -> None:
        self.conn, self.plans, self.tools, self.llm = conn, tuple(plans), dict(tools), llm

    async def collect(self, state: CollectState) -> dict[str, Collection]:
        return {
            "collection": await collect(
                self.plans, self.tools, self.llm, state["query"], state["as_of"]
            )
        }

    async def freeze(self, state: CollectState) -> dict[str, Bundle]:
        # Async node: keep SQLite on its owning event-loop thread, not a worker thread.
        collection = state["collection"]
        return {
            "bundle": freeze(
                self.conn, state["run_id"], collection.evidence, state["as_of"], collection.statuses
            )
        }
