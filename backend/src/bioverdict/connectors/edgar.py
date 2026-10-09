"""SEC EDGAR: what the sponsor told its investors about the asset (A10).

A company that files with the SEC reports material events in a form 8-K (a foreign issuer in a
form 6-K), usually with its press release attached as exhibit 99: trial readouts, regulatory
designations, clinical holds, programs it stops. This connector reads the newest such filings
of the asset's sponsor and keeps the paragraphs that name the asset.

Nothing here is searched by text (EDGAR's full-text search refuses automated requests). The
chain is made of identifiers:

1. the sponsor: the lead sponsor of the asset's studies in ClinicalTrials.gov;
2. its CIK: the SEC's own company list, matched by the whole company name, never by likeness;
3. its filings: `data.sec.gov/submissions`, then each filing's index and documents.

A sponsor that does not file with the SEC (Roche) gives nothing, and that is not an error.

A company's statement is not a finding. Every record has source kind `company` and the level
`registry_record`: it can support a fact about a program (stopped, started, designated), and it
adds no weight to a claim that the drug works. It shares the sponsor's independence group with
the registry records, so a company and its own registry entry count once.

The SEC asks for a declared contact and at most ten requests a second. `SEC_USER_AGENT`
("Name email") is required; without it nothing is read and the connector says so.
"""

from __future__ import annotations

import html
import json
import logging
import re
from collections import Counter
from datetime import date, datetime

import httpx

from bioverdict.connectors.clinicaltrials import ClinicalTrialsConnector
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.sponsors import company_key
from bioverdict.connectors.text import chunks
from bioverdict.connectors.validate import BodyError, json_object
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, ResolverOutput, SourceKind

log = logging.getLogger(__name__)

COMPANIES_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{folder}/{name}"
FAMILY = "sec_filing"
FORMS = ("8-K", "6-K")
# 8-K items under which a company reports on its pipeline: results of operations, Regulation
# FD disclosure, other events. Financing, governance and auditor items are not read.
EVENT_ITEMS = {"2.02", "7.01", "8.01"}
MAX_SPONSORS = 2
MAX_FILINGS = 8  # per sponsor, the newest first
MAX_EXHIBITS = 2  # per filing, beside its main document
MAX_PIECES = 2  # per document
HEADING_CHARS = 80  # a paragraph this short is read as a heading
MIN_NAME = 4  # characters; a shorter asset name would match unrelated words
_GENERIC = {"pharmaceuticals", "pharmaceutical", "pharma"}  # "Novartis Pharmaceuticals"
_EXHIBIT = re.compile(r"ex[-_]?99", re.IGNORECASE)
_DROPPED = re.compile(r"<(script|style|ix:header)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
_BREAK = re.compile(r"<br\s*/?>|</(?:p|div|tr|li|table|h[1-6])>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


def find_cik(sponsor: str, companies: dict) -> tuple[int, str] | None:
    """The CIK and the SEC's name of the one company whose name equals the sponsor's.

    Names are compared whole, without case, punctuation and legal form. If that finds nothing,
    a trailing "Pharmaceuticals" or "Pharma" is dropped on both sides (the registry names a
    subsidiary, the SEC the parent). Two different companies under one name give no answer.
    """

    def loose(key: str) -> str:
        words = key.split()
        while len(words) > 1 and words[-1] in _GENERIC:
            words.pop()
        return " ".join(words)

    wanted = company_key(sponsor)
    if not wanted:
        return None
    listed = [(int(c["cik_str"]), str(c["title"])) for c in companies.values()]
    for same in (lambda key: key == wanted, lambda key: loose(key) == loose(wanted)):
        found = {cik: title for cik, title in listed if same(company_key(title))}
        if len(found) == 1:
            return next(iter(found.items()))
        if found:
            return None
    return None


def event_filings(submissions: dict, as_of: date) -> list[dict]:
    """The newest filings that may report on the pipeline and were filed by the cutoff."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    rows = [dict(zip(recent, values, strict=True)) for values in zip(*recent.values(), strict=True)]
    kept = []
    for row in rows:
        try:
            filed = date.fromisoformat(str(row.get("filingDate")))
        except ValueError:
            continue
        items = set(str(row.get("items") or "").split(","))
        reports = row.get("form") == "6-K" or (row.get("form") == "8-K" and items & EVENT_ITEMS)
        if reports and filed <= as_of and row.get("accessionNumber"):
            kept.append(row | {"filed": filed})
    kept.sort(key=lambda row: (row["filed"], row["accessionNumber"]), reverse=True)
    return kept[:MAX_FILINGS]


def documents(index: dict, primary: str) -> list[str]:
    """The filing's main document and its first press-release exhibits (99.x)."""
    names = [str(item.get("name")) for item in (index.get("directory") or {}).get("item") or []]
    exhibits = sorted(n for n in names if _EXHIBIT.search(n) and n.lower().endswith(".htm"))
    wanted = [primary, *exhibits[:MAX_EXHIBITS]] if primary in names else exhibits[:MAX_EXHIBITS]
    return list(dict.fromkeys(wanted))


def paragraphs(page: bytes) -> list[str]:
    """The visible paragraphs of a filing document, markup and machine-readable header removed."""
    text = _DROPPED.sub(" ", page.decode("utf-8", "replace"))
    text = _TAG.sub(" ", _BREAK.sub("\n", text))
    lines = (" ".join(html.unescape(line).split()) for line in text.split("\n"))
    return [line for line in lines if line]


def naming(texts: list[str], assets: list[str]) -> list[str]:
    """The paragraphs that name the asset, in the document's order. A heading that names it
    ("Zoldonrasib in PDAC") brings the paragraph under it, which often says "the company" only.
    """
    names = [name.casefold() for name in assets if len(name.strip()) >= MIN_NAME]
    kept: dict[int, str] = {}
    for position, text in enumerate(texts):
        if any(name in text.casefold() for name in names):
            kept[position] = text
            if len(text) <= HEADING_CHARS and position + 1 < len(texts):
                kept[position + 1] = texts[position + 1]
    return [kept[position] for position in sorted(kept)]


class EdgarConnector:
    """Satisfies `Connector`. Reads the registry (from the cache when it ran first) for the
    sponsor, so it needs asset names; without them, or without a contact, nothing is read."""

    name = "sec_edgar"

    def __init__(
        self, http: CachedHttpClient, registry: ClinicalTrialsConnector, contact: str | None
    ) -> None:
        self._http = http
        self._registry = registry
        self._headers = {"User-Agent": contact} if contact and contact.strip() else None
        self.problems: list[str] = []

    async def _get(self, url: str, validate=None) -> tuple[bytes, datetime]:
        response = await self._http.get(url, validate=validate, headers=self._headers)
        return response.body, response.fetched_at

    async def _sponsors(self, query: ResolverOutput, as_of: date) -> list[str]:
        """The sponsors of the asset's studies, the one with most records first."""
        records = await self._registry.fetch(query, as_of)
        groups = Counter(
            record.independence_group.removeprefix("sponsor:")
            for record in records
            if record.independence_group.startswith("sponsor:")
            and record.independence_group != "sponsor:unknown"
        )
        return [name for name, _ in groups.most_common(MAX_SPONSORS)]

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        self.problems = []
        if not any(len(name.strip()) >= MIN_NAME for name in query.known_assets):
            return []  # no asset name long enough to recognise in a filing
        if self._headers is None:
            self.problems.append("SEC_USER_AGENT is not set: the SEC was not asked")
            return []
        sponsors = await self._sponsors(query, as_of)
        if not sponsors:
            return []
        companies = json.loads((await self._get(COMPANIES_URL, json_object()))[0])
        evidence: list[Evidence] = []
        for sponsor in sponsors:
            company = find_cik(sponsor, companies)
            if company is None:
                continue  # not an SEC registrant under this name
            cik, title = company
            body, _ = await self._get(SUBMISSIONS_URL.format(cik=cik), json_object("filings"))
            for filing in event_filings(json.loads(body), as_of):
                evidence += await self._filing(cik, title, sponsor, filing, query.known_assets)
        return evidence

    async def _filing(
        self, cik: int, company: str, sponsor: str, filing: dict, assets: list[str]
    ) -> list[Evidence]:
        accession = filing["accessionNumber"]
        folder = accession.replace("-", "")
        try:
            index_url = ARCHIVE_URL.format(cik=cik, folder=folder, name="index.json")
            index = json.loads((await self._get(index_url, json_object("directory")))[0])
            found: list[Evidence] = []
            for name in documents(index, str(filing.get("primaryDocument") or "")):
                url = ARCHIVE_URL.format(cik=cik, folder=folder, name=name)
                page, fetched_at = await self._get(url)
                pieces = chunks("\n".join(naming(paragraphs(page), assets)))
                if len(pieces) > MAX_PIECES:
                    self.problems.append(f"filing {accession} ({name}) was read in part")
                for number, piece in enumerate(pieces[:MAX_PIECES], start=1):
                    found.append(
                        Evidence(
                            id=f"sec:{accession}:{name}:{number}",  # placeholder until the freeze
                            source=f"SEC EDGAR {filing['form']} of {company}",
                            source_family=FAMILY,
                            source_kind=SourceKind.COMPANY,
                            url=url,
                            locator=Locator(
                                type="sec_accession", value=f"{accession}:{name}#{number}"
                            ),
                            excerpt=piece,
                            published_at=filing["filed"],
                            retrieved_at=fetched_at,
                            level=EvidenceLevel.REGISTRY_RECORD,
                            independence_group=f"sponsor:{sponsor}",
                            version=1,
                        )
                    )
            return found
        except (httpx.HTTPError, BodyError, ValueError) as exc:
            log.warning("filing %s not read: %s", accession, type(exc).__name__)
            self.problems.append(f"filing {accession} could not be read")
            return []
