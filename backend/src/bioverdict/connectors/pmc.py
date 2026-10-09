"""PubMed Central open access: the results of a paper, not only its abstract (A6).

An abstract gives a paper's headline; response rates by subgroup, exposure, biomarker changes and
safety tables are in the full text. For the strongest and newest papers the PubMed connector
found, this connector asks NCBI's BioC service for the full text and keeps the Results section
and the tables, in pieces a model picks quotes from.

A piece is evidence of the same paper as its abstract: it copies the paper's level, kind, date
and independence group, so a paper read twice still counts once.

Only papers whose licence allows reuse without a non-commercial or no-derivatives condition
(CC BY, CC0) are read; the open-access subset also holds CC BY-NC-ND papers, and those are left
with their abstract. A paper that is not in the subset simply has no full text here.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date

import httpx

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.pubmed import PubMedConnector
from bioverdict.connectors.text import chunks
from bioverdict.connectors.validate import BodyError
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, ResolverOutput

log = logging.getLogger(__name__)

BIOC_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json"
ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/"
NOT_FOUND = b"[Error] : No result can be found"  # the service's answer for a paper it lacks
MAX_PAPERS = 4  # full texts read per run
MAX_ASKED = 8  # papers asked for before giving up on finding that many
MAX_PIECES = 3  # per paper; three papers' worth of text fill the extraction prompts
READ_SECTIONS = ("RESULTS", "TABLE")

_OPEN = re.compile(
    r"creativecommons\.org/(?:licenses/by/|publicdomain/zero)|\bCC[ -]?BY\b|\bCC0\b", re.IGNORECASE
)
_RESTRICTED = re.compile(r"\bNC\b|\bND\b|non-?commercial|no-?deriv|by-nc|by-nd", re.IGNORECASE)
_STRENGTH = {level: rank for rank, level in enumerate(EvidenceLevel)}  # strongest first


def require_document(body: bytes) -> None:
    """A BioC collection, or the service's plain "no result" (a valid, cacheable answer)."""
    if body.startswith(NOT_FOUND):
        return
    try:
        answer = json.loads(body)
        answer[0]["documents"][0]["passages"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise BodyError("the answer is not a full-text document") from exc


def reusable(licence: str | None) -> bool:
    """Whether the licence text names an open licence and no condition that restricts reuse."""
    return bool(licence) and bool(_OPEN.search(licence)) and not _RESTRICTED.search(licence)


def parse_full_text(body: bytes, paper: Evidence) -> tuple[list[Evidence], bool]:
    """The Results text and the tables of `paper` as evidence, and whether any was left out.

    Empty when the paper is not in the open-access subset or its licence restricts reuse.
    """
    if body.startswith(NOT_FOUND):
        return [], False
    document = json.loads(body)[0]["documents"][0]
    passages = document.get("passages") or []
    front = (passages[0].get("infons") or {}) if passages else {}
    number = re.sub(
        r"\D", "", str(front.get("article-id_pmc") or front.get("article-id_pmcid") or "")
    )
    if not number or not reusable(front.get("license")):
        return [], False
    pmcid = f"PMC{number}"
    # Results first: when a paper is too long, its tables are what is left unread.
    wanted = sorted(
        (p for p in passages if (p.get("infons") or {}).get("section_type") in READ_SECTIONS),
        key=lambda p: READ_SECTIONS.index(p["infons"]["section_type"]),
    )
    pieces = chunks("\n".join(p.get("text") or "" for p in wanted))
    evidence = [
        paper.model_copy(
            update={
                "id": f"{paper.id}:fulltext:{n}",  # placeholder, replaced at the freeze
                "source": "PubMed Central (open-access full text)",
                "url": f"{ARTICLE_URL}{pmcid}/",
                "locator": Locator(type="pmcid", value=f"{pmcid}#results:{n}"),
                "excerpt": piece,
            }
        )
        for n, piece in enumerate(pieces[:MAX_PIECES], start=1)
    ]
    return evidence, len(pieces) > MAX_PIECES


def by_strength(papers: list[Evidence], assets: list[str] | None = None) -> list[Evidence]:
    """The papers whose full text matters most, first: those that name the asset (the others
    are about its class), then findings in humans, then the newest."""
    names = [name.casefold() for name in assets or [] if name.strip()]
    return sorted(
        papers,
        key=lambda p: (
            not any(name in p.excerpt.casefold() for name in names),
            _STRENGTH[p.level],
            -(p.published_at or p.retrieved_at.date()).toordinal(),
            p.id,
        ),
    )


class PmcFullTextConnector:
    """Satisfies `Connector`. Reads full texts of the papers `pubmed` finds for the same query
    (its searches are answered from the cache when the PubMed connector ran first)."""

    name = "pmc_fulltext"

    def __init__(self, http: CachedHttpClient, pubmed: PubMedConnector) -> None:
        self._http = http
        self._pubmed = pubmed
        self.problems: list[str] = []

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        self.problems = []
        evidence: list[Evidence] = []
        read = 0
        papers = by_strength(await self._pubmed.fetch(query, as_of), query.known_assets)
        for paper in papers[:MAX_ASKED]:
            if read == MAX_PAPERS or paper.locator is None:
                break
            pmid = paper.locator.value
            try:
                response = await self._http.get(
                    f"{BIOC_URL}/{pmid}/unicode", validate=require_document
                )
            except (httpx.HTTPError, BodyError) as exc:
                log.warning("full text of PMID %s not read: %s", pmid, type(exc).__name__)
                self.problems.append(f"full text of PMID {pmid} could not be read")
                continue
            pieces, cut = parse_full_text(response.body, paper)
            if cut:
                self.problems.append(f"full text of PMID {pmid} was read in part")
            evidence += pieces
            read += bool(pieces)
        return evidence
