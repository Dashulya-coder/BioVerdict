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

from bioverdict import settings
from bioverdict.agents.collect import CollectPlan
from bioverdict.connectors.clinicaltrials import ClinicalTrialsConnector
from bioverdict.connectors.epidemiology import (
    CancerIncidenceConnector,
    CdcIndicatorsConnector,
    OrphanetConnector,
    PopulationConnector,
)
from bioverdict.connectors.europepmc import EuropePmcConnector
from bioverdict.connectors.http import DEFAULT_MIN_INTERVAL_S, CachedHttpClient
from bioverdict.connectors.openfda import OpenFdaConnector
from bioverdict.connectors.opentargets import OpenTargetsApi, OpenTargetsConnector
from bioverdict.connectors.pmc import PmcFullTextConnector
from bioverdict.connectors.pricing import AnalogPricingConnector
from bioverdict.connectors.pubmed import PubMedConnector
from bioverdict.connectors.retry import MAX_ATTEMPTS
from bioverdict.contracts import Connector
from bioverdict.resolver.lookup import OpenTargetsLookup
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.models import Evidence, ResolverOutput, Section

HTTP_TIMEOUT_S = 30
NO_INDICATION = "not specified"  # what the Resolver writes when the input names no disease

# Translation is reasoned from the mechanism and clinical evidence; it has no source of its own.
LIVE_PLANS = (
    # Preprints are mostly laboratory work on the mechanism; published papers are in PubMed.
    CollectPlan(section=Section.MECHANISM, tools=("opentargets", "europepmc")),
    # Full texts last: they repeat PubMed's searches from the cache, and if the section's time
    # runs out it is the abstracts and the registry that have been read.
    CollectPlan(section=Section.CLINICAL, tools=("clinicaltrials", "pubmed", "pmc_fulltext")),
    # The class in the registry, then what the FDA approved in it and what those labels say.
    CollectPlan(section=Section.COMPETITION, tools=("clinicaltrials_class", "openfda")),
    # Market records are status facts: stored whole, read by code (`market/tam.py`), no model.
    CollectPlan(
        section=Section.COMMERCIAL,
        tools=("analog_pricing", "cancer_incidence", "cdc_indicators", "orphanet", "population"),
    ),
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


def paced_sources(
    min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
    max_attempts: int = MAX_ATTEMPTS,
    refresh: bool = False,
) -> SourcesFactory:
    """The public sources: Open Targets, ClinicalTrials.gov, PubMed, Europe PMC, openFDA and the market
    sources. None needs a key; `NCBI_API_KEY` and `OPENFDA_API_KEY` only raise the limits.

    A run keeps the default pace, which fits its time budget. Reading many assets in a row
    (`bioverdict warm`) has to be slower and more patient, or the registry answers 429.
    Cached answers are reused for as long as `HTTP_CACHE_MAX_AGE_H` allows (for ever when it is
    unset); `refresh` downloads everything again and replaces what was cached.
    """

    @asynccontextmanager
    async def opened(conn: sqlite3.Connection) -> AsyncIterator[Sources]:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
            http = CachedHttpClient(
                client,
                HttpCache(conn),
                min_interval_s=min_interval_s,
                max_attempts=max_attempts,
                max_age_s=0 if refresh else settings.http_cache_max_age_s(),
            )
            yield _sources(http)

    return opened


def _sources(http: CachedHttpClient) -> Sources:
    pubmed = PubMedConnector(http, api_key=os.environ.get("NCBI_API_KEY") or None)
    tools: list[Connector] = [
        OpenTargetsConnector(http),
        ClinicalTrialsConnector(http),
        TargetClassTrials(ClinicalTrialsConnector(http)),
        pubmed,
        PmcFullTextConnector(http, pubmed),
        EuropePmcConnector(http),
        OpenFdaConnector(http, api_key=os.environ.get("OPENFDA_API_KEY") or None),
        AnalogPricingConnector(http),
        CancerIncidenceConnector(http),
        CdcIndicatorsConnector(http),
        OrphanetConnector(http),
        PopulationConnector(http),
    ]
    return Sources(
        lookup=OpenTargetsLookup(OpenTargetsApi(http)),
        tools={tool.name: tool for tool in tools},
    )


live_sources = paced_sources()
