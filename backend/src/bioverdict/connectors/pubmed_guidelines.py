"""PubMed practice guidelines for the indication: what the standard of care is, in its own words.

The unmet-need module has to say what treats the disease today and where that falls short. A
guideline is where a specialty society writes that down, and PubMed labels such papers
`Practice Guideline`. `PubMedConnector` leaves them out on purpose (they restate trials, so
counting them next to the trials would count a finding twice); this connector reads only them, for
the indication and never for the asset, and the evidence it makes answers a different question.

What a guideline is cannot be put on the strength scale exactly: it summarises evidence and adds
a panel's judgement. Its level here is `human_observational`, a guess that keeps it from weighing
like a trial, and its independence group is its own, so two guidelines count twice. It is a
consensus statement, not a measurement: the module that reads it must not use it as proof that a
drug works.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, datetime

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.pubmed import (
    ARTICLE_URL,
    BASE_URL,
    TOOL,
    _abstract,
    _entrez_date,
    _quote,
    _text,
    require_articles,
    require_search_result,
)
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Locator,
    ResolverOutput,
    SourceKind,
)

FAMILY = "literature"
RETMAX = 6  # the newest guidelines: an older one is replaced by its update
NO_INDICATION = "not specified"
_GUIDELINE_TYPES = {"Practice Guideline", "Guideline"}


def build_term(indication: str) -> str:
    """The indication is not quoted, so that PubMed maps it to its MeSH heading and synonyms:
    the disease term of Open Targets ("non-small cell lung carcinoma") is not the one the
    guidelines use in their titles ("non-small cell lung cancer"), and a quoted phrase finds only
    old papers."""
    return f"{_quote(indication)} AND (Practice Guideline[pt] OR Guideline[pt])"


def parse_guidelines(xml: bytes | str, retrieved_at: datetime) -> list[Evidence]:
    """One evidence per guideline that has an abstract, by its title and abstract."""
    evidence = []
    for article in ET.fromstring(xml).findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID", "").strip()
        title = _text(article.find(".//ArticleTitle"))
        abstract = _abstract(article)
        types = {_text(t) for t in article.findall(".//PublicationTypeList/PublicationType")}
        if not pmid or not abstract or not (_GUIDELINE_TYPES & types):
            continue
        evidence.append(
            Evidence(
                id=f"pmid:{pmid}",  # placeholder, replaced when the bundle is frozen
                source="PubMed (practice guideline)",
                source_family=FAMILY,
                source_kind=SourceKind.PEER_REVIEWED,
                url=f"{ARTICLE_URL}{pmid}/",
                locator=Locator(type="pmid", value=pmid),
                excerpt=f"{title}\n{abstract}" if title else abstract,
                published_at=_entrez_date(article),
                retrieved_at=retrieved_at,
                level=EvidenceLevel.HUMAN_OBSERVATIONAL,
                independence_group=f"guideline:{pmid}",
                version=1,
            )
        )
    return evidence


class PubMedGuidelinesConnector:
    """Satisfies `Connector`. At most `retmax` guidelines, newest first; nothing without an
    indication."""

    name = "pubmed_guidelines"

    def __init__(
        self, http: CachedHttpClient, retmax: int = RETMAX, api_key: str | None = None
    ) -> None:
        self._http = http
        self._retmax = retmax
        self._identity = {"tool": TOOL}
        if api_key:
            self._identity["api_key"] = api_key

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        indication = query.indication.name
        if not indication.strip() or indication == NO_INDICATION:
            return []
        params = {
            **self._identity,
            "db": "pubmed",
            "term": build_term(indication),
            "retmax": str(self._retmax),
            "sort": "pub_date",
            "retmode": "json",
        }
        found = await self._http.get(
            f"{BASE_URL}/esearch.fcgi", params, validate=require_search_result
        )
        ids = json.loads(found.body)["esearchresult"].get("idlist", [])
        if not ids:
            return []
        fetched = await self._http.get(
            f"{BASE_URL}/efetch.fcgi",
            {**self._identity, "db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            validate=require_articles,
        )
        return filter_as_of(parse_guidelines(fetched.body, fetched.fetched_at), as_of)
