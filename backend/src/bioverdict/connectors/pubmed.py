"""PubMed (NCBI E-utilities): papers that report what was found.

Searches and reads articles; every article with an abstract becomes one evidence item whose
excerpt is its title and abstract, so a quote can be an exact substring of it. Without a
credential the service allows about three requests a second, which `CachedHttpClient` paces.

What kind of evidence a paper is cannot be known exactly from its record. The level here is a
conservative guess from PubMed's own labels, never a judgement of the result:
- a clinical trial or randomised trial: `human_interventional`;
- a genome-wide association or Mendelian randomisation study: `human_genetics`;
- an observational study, a case report or a meta-analysis: `human_observational`;
- animal MeSH terms: `animal_in_vivo`;
- anything else (basic research, methods, manufacturing): `in_vitro`, the weakest level.
Reviews, editorials, comments, letters and news are left out: they restate other papers, so
counting them would count the same finding twice.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import date, datetime

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Locator,
    ResolverOutput,
    SourceKind,
)

BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
ARTICLE_URL = "https://pubmed.ncbi.nlm.nih.gov/"
TOOL = "bioverdict-hackathon"
RETMAX = 20
FETCH_BATCH = 50
TRIAL_FILTER = "(clinical trial[pt] OR randomized controlled trial[pt])"
REVIEW_GROUP = "review:class-safety"  # every review of a safety search is one source
SAFETY_FILTER = (
    '(hepatotoxicity[tiab] OR "liver injury"[tiab] OR "liver enzyme*"[tiab] OR hepatic[tiab] '
    'OR "liver safety"[tiab] OR cardiotoxicity[tiab] OR "adverse events"[tiab] '
    'OR "drug safety"[tiab] OR "safety profile"[tiab])'
)
SAFETY_RETMAX = 10

_SKIP_TYPES = {
    "Review",
    "Systematic Review",
    "Editorial",
    "Comment",
    "Letter",
    "News",
    "Interview",
    "Biography",
    "Congress",
    "Published Erratum",
    "Retraction of Publication",
    "Retracted Publication",
    "Practice Guideline",
    "Guideline",
}
_OBSERVATIONAL_TYPES = {"Observational Study", "Case Reports", "Meta-Analysis"}
_GENETICS_MESH = {
    "Genome-Wide Association Study",
    "Mendelian Randomization Analysis",
}
_ANIMAL_MESH = {
    "Animals",
    "Mice",
    "Rats",
    "Disease Models, Animal",
    "Xenograft Model Antitumor Assays",
}


class PubMedError(ValueError):
    """PubMed answered HTTP 200 with something that is not the data that was asked for."""


def require_search_result(body: bytes) -> None:
    """Refuse a search answer without an id list. NCBI reports a rate limit and a bad query
    inside a 200 answer; cached, it would be replayed as "no papers" for ever."""
    try:
        result = json.loads(body)["esearchresult"]
    except (ValueError, KeyError, TypeError) as exc:
        raise PubMedError("the search answer has no result") from exc
    if not isinstance(result, dict) or "ERROR" in result or "idlist" not in result:
        raise PubMedError("the search answer has no id list")


def require_articles(body: bytes) -> None:
    """Refuse a fetch answer that is not an article set (an error page, a cut-off download)."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise PubMedError("the fetch answer is not XML") from exc
    if root.tag != "PubmedArticleSet":
        raise PubMedError("the fetch answer is not an article set")


_REVIEW_TYPES = {"Review", "Systematic Review"}


def classify(
    types: list[str], mesh: list[str], reviews: bool = False
) -> tuple[EvidenceLevel, SourceKind] | None:
    """The level and kind of a paper from its PubMed labels, or None for a paper to skip.

    With `reviews` a review is kept, as a human observational source: it restates what other
    papers found, so it may say what a class has done to patients but never count as new data.
    """
    if _SKIP_TYPES - (_REVIEW_TYPES if reviews else set()) & set(types):
        return None
    if reviews and _REVIEW_TYPES & set(types):
        kind = SourceKind.PREPRINT if "Preprint" in types else SourceKind.PEER_REVIEWED
        return EvidenceLevel.HUMAN_OBSERVATIONAL, kind
    kind = SourceKind.PREPRINT if "Preprint" in types else SourceKind.PEER_REVIEWED
    if any(t.startswith("Clinical Trial") or t.endswith("Controlled Trial") for t in types):
        return EvidenceLevel.HUMAN_INTERVENTIONAL, kind
    if _GENETICS_MESH & set(mesh):
        return EvidenceLevel.HUMAN_GENETICS, kind
    if _OBSERVATIONAL_TYPES & set(types):
        return EvidenceLevel.HUMAN_OBSERVATIONAL, kind
    if _ANIMAL_MESH & set(mesh):
        return EvidenceLevel.ANIMAL_IN_VIVO, kind
    return EvidenceLevel.IN_VITRO, kind


def _text(element: ET.Element | None) -> str:
    """All the text of an element, including text inside inline tags such as <i> and <sup>."""
    return " ".join("".join(element.itertext()).split()) if element is not None else ""


def _abstract(article: ET.Element) -> str:
    parts = []
    for section in article.findall(".//Abstract/AbstractText"):
        text = _text(section)
        if not text:
            continue
        label = section.get("Label")
        parts.append(f"{label}: {text}" if label else text)
    return "\n".join(parts)


def _entrez_date(article: ET.Element) -> date | None:
    """The day PubMed recorded the article: always present, and never later than its release."""
    for item in article.findall(".//PubmedData/History/PubMedPubDate"):
        if item.get("PubStatus") == "entrez":
            try:
                return date(
                    int(item.findtext("Year", "0")),
                    int(item.findtext("Month", "0")),
                    int(item.findtext("Day", "0")),
                )
            except ValueError:
                return None
    return None


def _trial_ids(article: ET.Element) -> list[str]:
    ids = []
    for bank in article.findall(".//DataBankList/DataBank"):
        if bank.findtext("DataBankName") == "ClinicalTrials.gov":
            ids += [n.text for n in bank.findall(".//AccessionNumber") if n.text]
    return ids


def parse_articles(
    xml: bytes | str, retrieved_at: datetime, reviews: bool = False
) -> list[Evidence]:
    """One evidence per article that has an abstract and is not a review, letter or similar.

    With `reviews` a review is kept, and all the reviews of a search share one independence
    group, so that however many of them say the same thing it counts once.
    """
    root = ET.fromstring(xml)
    evidence = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//MedlineCitation/PMID", "").strip()
        title = _text(article.find(".//ArticleTitle"))
        abstract = _abstract(article)
        types = [_text(t) for t in article.findall(".//PublicationTypeList/PublicationType")]
        mesh = [_text(m) for m in article.findall(".//MeshHeadingList/MeshHeading/DescriptorName")]
        classified = classify(types, mesh, reviews)
        if not pmid or not abstract or classified is None:
            continue
        level, kind = classified
        trials = _trial_ids(article)
        review = reviews and bool(_REVIEW_TYPES & set(types))
        evidence.append(
            Evidence(
                id=f"pmid:{pmid}",  # placeholder, replaced when the bundle is frozen
                source="PubMed",
                source_family="literature",
                source_kind=kind,
                url=f"{ARTICLE_URL}{pmid}/",
                locator=Locator(type="pmid", value=pmid),
                excerpt=f"{title}\n{abstract}" if title else abstract,
                published_at=_entrez_date(article),
                retrieved_at=retrieved_at,
                level=level,
                # Papers on one trial report one dataset: they share a group and count once.
                independence_group=(
                    REVIEW_GROUP if review else f"trial:{trials[0]}" if trials else f"paper:{pmid}"
                ),
                version=1,
            )
        )
    return evidence


def _quote(name: str) -> str:
    """A name safe to place inside a PubMed phrase: no quotes or brackets that end it early."""
    return " ".join(name.replace('"', " ").replace("[", " ").replace("]", " ").split())


def safety_terms(query: ResolverOutput) -> list[str]:
    """What is known of the harm of the asset and of its class: the asset (or the target class
    within the indication) together with the words of toxicity, liver and adverse events."""
    names = [n for n in dict.fromkeys(_quote(a) for a in query.known_assets) if n]
    symbols = [_quote(t.symbol) for t in query.targets if t.symbol]
    indication = _quote(query.indication.name)
    terms: list[str] = []
    if names:
        asset = " OR ".join(f'"{name}"[Title/Abstract]' for name in names)
        terms.append(f"({asset}) AND {SAFETY_FILTER}")
    if symbols and indication and indication != "not specified":
        terms.append(f'({" OR ".join(symbols)}) AND "{indication}" AND {SAFETY_FILTER}')
    return terms


def build_terms(query: ResolverOutput) -> list[str]:
    """Search terms: the assets (every paper, then only trials) and the class of the target.

    The class term finds the trials of other drugs against the same target in the same
    indication, which is where failed analogs and benchmarks come from.
    """
    terms: list[str] = []
    names = [n for n in dict.fromkeys(_quote(a) for a in query.known_assets) if n]
    if names:
        asset = " OR ".join(f'"{name}"[Title/Abstract]' for name in names)
        terms += [f"({asset})", f"({asset}) AND {TRIAL_FILTER}"]

    symbols = [_quote(t.symbol) for t in query.targets if t.symbol]
    indication = _quote(query.indication.name)
    if symbols and indication and indication != "not specified":
        targets = " OR ".join(symbols)
        terms.append(f"({targets}) AND {indication} AND {TRIAL_FILTER}")
    return terms


class PubMedConnector:
    """Satisfies `Connector`. At most `retmax` papers per search term."""

    name = "pubmed"

    def __init__(
        self,
        http: CachedHttpClient,
        retmax: int = RETMAX,
        email: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._http = http
        self._retmax = retmax
        self._identity = {"tool": TOOL}
        if email:
            self._identity["email"] = email
        if api_key:
            self._identity["api_key"] = api_key

    async def _search(self, term: str) -> list[str]:
        params = {
            **self._identity,
            "db": "pubmed",
            "term": term,
            "retmax": str(self._retmax),
            "retmode": "json",
        }
        response = await self._http.get(
            f"{BASE_URL}/esearch.fcgi", params, validate=require_search_result
        )
        return json.loads(response.body)["esearchresult"].get("idlist", [])

    reviews = False  # whether a review is kept (see `parse_articles`)

    def terms(self, query: ResolverOutput) -> list[str]:
        return build_terms(query)

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        pmids: dict[str, None] = {}  # in order of first appearance, each paper once
        for term in self.terms(query):
            for pmid in await self._search(term):
                pmids.setdefault(pmid)

        evidence: list[Evidence] = []
        ids = list(pmids)
        for start in range(0, len(ids), FETCH_BATCH):
            params = {
                **self._identity,
                "db": "pubmed",
                "id": ",".join(ids[start : start + FETCH_BATCH]),
                "retmode": "xml",
            }
            response = await self._http.get(
                f"{BASE_URL}/efetch.fcgi", params, validate=require_articles
            )
            evidence += parse_articles(response.body, response.fetched_at, self.reviews)
        return filter_as_of(evidence, as_of)


class PubMedSafetyConnector(PubMedConnector):
    """Satisfies `Connector`. The safety of the asset and of its class, reviews included.

    The ordinary search leaves reviews out; a review is often where the harm of a class (a liver
    signal across a drug class) is written down. All of them count as one source.
    """

    name = "pubmed_safety"
    reviews = True

    def __init__(self, http: CachedHttpClient, **kwargs) -> None:
        kwargs.setdefault("retmax", SAFETY_RETMAX)
        super().__init__(http, **kwargs)

    def terms(self, query: ResolverOutput) -> list[str]:
        return safety_terms(query)
