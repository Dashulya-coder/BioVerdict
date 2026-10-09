"""Europe PMC: preprints, which PubMed does not carry (A6).

Only preprints are read here (bioRxiv, medRxiv, Research Square and others): published papers
come from the PubMed connector, and reading them twice would count one finding twice. Every
preprint with an abstract becomes one evidence item whose excerpt is its title and abstract with
the markup removed, so a quote can be an exact substring of it.

A preprint is not peer reviewed and its record does not say what kind of study it is, so every
one gets the weakest level (`in_vitro`) and the source kind `preprint`. That is a floor, not a
judgement: a clinical preprint is under-weighted until its paper is in PubMed. A preprint and its
later paper are not linked here, so the two can appear as separate sources.
"""

from __future__ import annotations

import html
import json
import re
from datetime import date, datetime

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, ResolverOutput, SourceKind

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
DOI_URL = "https://doi.org/"
RECORD_URL = "https://europepmc.org/article/PPR/"
PAGE_SIZE = 20  # per search term, newest first
NO_INDICATION = "not specified"  # what the Resolver writes when the input names no disease
_TAG = re.compile(r"<[^>]+>")


class EuropePmcError(ValueError):
    """Europe PMC answered with something that is not a result list."""


def require_results(body: bytes) -> None:
    """Refuse a body without a result list, so that an error page is never cached."""
    try:
        answer = json.loads(body)
        results = answer["resultList"]["result"]
    except (ValueError, KeyError, TypeError) as exc:
        raise EuropePmcError("the answer has no result list") from exc
    if not isinstance(results, list):
        raise EuropePmcError("the answer has no result list")


def plain(text: str) -> str:
    """Text without markup: `KRAS <sup>G12C</sup>` reads `KRAS G12C`, headings become words."""
    return " ".join(html.unescape(_TAG.sub(" ", text)).split())


def _day(text: object) -> date | None:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def parse_preprints(answer: dict, retrieved_at: datetime) -> list[Evidence]:
    """One evidence per preprint that has an abstract and a first publication date."""
    evidence = []
    for record in (answer.get("resultList") or {}).get("result") or []:
        ppr = str(record.get("id") or "")
        abstract = plain(record.get("abstractText") or "")
        published = _day(record.get("firstPublicationDate"))
        if record.get("source") != "PPR" or not ppr or not abstract or published is None:
            continue
        title, doi = plain(record.get("title") or ""), record.get("doi")
        server = (record.get("bookOrReportDetails") or {}).get("publisher")
        evidence.append(
            Evidence(
                id=f"ppr:{ppr}",  # placeholder, replaced when the bundle is frozen
                source=f"Europe PMC preprint ({server})" if server else "Europe PMC preprint",
                source_family="preprint",
                source_kind=SourceKind.PREPRINT,
                url=f"{DOI_URL}{doi}" if doi else f"{RECORD_URL}{ppr}",
                locator=Locator(type="doi", value=doi) if doi else Locator(type="ppr", value=ppr),
                excerpt=f"{title}\n{abstract}" if title else abstract,
                published_at=published,
                retrieved_at=retrieved_at,
                level=EvidenceLevel.IN_VITRO,
                independence_group=f"preprint:{ppr}",
                version=1,
            )
        )
    return evidence


def _phrase(name: str) -> str:
    """A name safe inside a quoted phrase of the search language."""
    return " ".join(re.sub(r'["()\[\]\\:]', " ", name).split())


def build_queries(query: ResolverOutput) -> list[str]:
    """Preprints that name the asset; without an asset, those on the target in the indication."""
    names = [n for n in dict.fromkeys(_phrase(a) for a in query.known_assets) if n]
    if names:
        asset = " OR ".join(f'TITLE:"{n}" OR ABSTRACT:"{n}"' for n in names)
        return [f"({asset}) AND SRC:PPR"]
    symbols = [s for s in dict.fromkeys(_phrase(t.symbol) for t in query.targets) if s]
    indication = _phrase(query.indication.name)
    if not symbols or not indication or indication == NO_INDICATION:
        return []
    targets = " OR ".join(f'TITLE:"{s}"' for s in symbols)
    return [f'({targets}) AND (TITLE:"{indication}" OR ABSTRACT:"{indication}") AND SRC:PPR']


class EuropePmcConnector:
    """Satisfies `Connector`. At most `page_size` preprints per search, the newest first."""

    name = "europepmc"

    def __init__(self, http: CachedHttpClient, page_size: int = PAGE_SIZE) -> None:
        self._http = http
        self._page_size = page_size

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        found: dict[str, Evidence] = {}  # each preprint once
        for term in build_queries(query):
            params = {
                "query": term,
                "format": "json",
                "resultType": "core",
                "pageSize": str(self._page_size),
                "sort": "FIRST_PDATE_D desc",
            }
            response = await self._http.get(SEARCH_URL, params, validate=require_results)
            for item in parse_preprints(json.loads(response.body), response.fetched_at):
                found.setdefault(item.id, item)
        return filter_as_of(list(found.values()), as_of)
