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


CLASS_STUDIES = 12  # of each kind; two records a study keeps the search inside the limits
_STOPPED = ("TERMINATED", "WITHDRAWN", "SUSPENDED")
_PHASES = ("PHASE3", "PHASE2")  # latest first; anything else ranks after them


def class_records(records: list[Evidence]) -> list[Evidence]:
    """The status and design of the studies that say most about a target class.

    A class search returns hundreds of records. What the competition section needs from a study
    is its phase, its status and why it stopped, so only those two records are kept, for the
    stopped studies (failed analogs) and for the others (competitors), latest phase and newest
    first, up to `CLASS_STUDIES` of each.
    """
    studies: dict[str, list[Evidence]] = {}
    for record in records:
        key = record.status_key or ""
        if record.locator is not None and key.endswith((":overall_status", ":design")):
            studies.setdefault(record.locator.value, []).append(record)

    def rank(nct: str) -> tuple[int, int, str]:
        text = " ".join(part.excerpt for part in studies[nct])
        phase = next((n for n, name in enumerate(_PHASES) if name in text), len(_PHASES))
        newest = max((p.published_at or p.retrieved_at.date()).toordinal() for p in studies[nct])
        return (phase, -newest, nct)

    def stopped(nct: str) -> bool:
        return any(word in part.excerpt for part in studies[nct] for word in _STOPPED)

    ordered = sorted(studies, key=rank)
    chosen = [n for n in ordered if stopped(n)][:CLASS_STUDIES]
    chosen += [n for n in ordered if not stopped(n)][:CLASS_STUDIES]
    return [part for nct in chosen for part in studies[nct]]


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
        return class_records(await self._registry.fetch(by_class, as_of))


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
