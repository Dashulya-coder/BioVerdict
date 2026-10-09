"""What a live run may read: the Resolver's lookup, the connectors and the collection plan.

Everything shares one cached HTTP client, so a repeated run is answered from the cache and the
hosts are paced. This is the allowlist of the run: a section that is not planned here stays
`not_searched`, and no tool outside `tools` can be called.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from datetime import date

import httpx

from bioverdict.agents.collect import CollectPlan
from bioverdict.connectors.clinicaltrials import ClinicalTrialsConnector
from bioverdict.connectors.http import DEFAULT_MIN_INTERVAL_S, CachedHttpClient
from bioverdict.connectors.opentargets import OpenTargetsApi, OpenTargetsConnector
from bioverdict.connectors.pubmed import PubMedConnector
from bioverdict.contracts import Connector
from bioverdict.resolver.lookup import OpenTargetsLookup
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.models import Evidence, ResolverOutput, Section

HTTP_TIMEOUT_S = 30
NO_INDICATION = "not specified"  # what the Resolver writes when the input names no disease

# Translation is reasoned from the mechanism and clinical evidence; it has no source of its own.
LIVE_PLANS = (
    CollectPlan(section=Section.MECHANISM, tools=("opentargets",)),
    CollectPlan(section=Section.CLINICAL, tools=("clinicaltrials", "pubmed")),
    CollectPlan(section=Section.COMPETITION, tools=("clinicaltrials_class",)),
)


class TargetClassTrials:
    """Satisfies `Connector`. The registry asked about the target class, not about the asset.

    Without asset names the registry connector searches the target within the indication, which
    is where competitors and stopped analogs are. Nothing is searched without an indication.
    """

    name = "clinicaltrials_class"

    def __init__(self, registry: ClinicalTrialsConnector) -> None:
        self._registry = registry

    @property
    def problems(self) -> list[str]:
        return self._registry.problems

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        if query.indication.name == NO_INDICATION:
            return []
        by_class = query.model_copy(update={"known_assets": [], "assets": []})
        return await self._registry.fetch(by_class, as_of)


@dataclass(frozen=True)
class Sources:
    lookup: OpenTargetsLookup
    tools: Mapping[str, Connector]
    plans: Sequence[CollectPlan] = LIVE_PLANS


# Opened inside the run's event loop and closed with it: an HTTP client belongs to one loop.
SourcesFactory = Callable[[sqlite3.Connection], AbstractAsyncContextManager[Sources]]


@asynccontextmanager
async def live_sources(conn: sqlite3.Connection) -> AsyncIterator[Sources]:
    """The public sources: Open Targets, ClinicalTrials.gov and PubMed. None needs a key."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
        http = CachedHttpClient(client, HttpCache(conn), min_interval_s=DEFAULT_MIN_INTERVAL_S)
        tools: list[Connector] = [
            OpenTargetsConnector(http),
            ClinicalTrialsConnector(http),
            TargetClassTrials(ClinicalTrialsConnector(http)),
            PubMedConnector(http, api_key=os.environ.get("NCBI_API_KEY") or None),
        ]
        yield Sources(
            lookup=OpenTargetsLookup(OpenTargetsApi(http)),
            tools={tool.name: tool for tool in tools},
        )
