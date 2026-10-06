"""ClinicalTrials.gov v2: turns study records into Evidence.

Per study this yields: the brief summary, each primary outcome, the status (with the reason a
trial was stopped, when given) and the design. Structured parts are stored as a JSON fragment
of the API response, so a quote can be an exact substring of the excerpt.

Status and design change over time, so they carry a `status_key` and a newer record replaces
an older one. The public API has no record history, so a status can only be as recent as the
record's last update: for an earlier `as_of` it is filtered out rather than guessed.
"""

from __future__ import annotations

import calendar
import json
from datetime import UTC, date, datetime

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.sponsors import sponsor_group
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Locator,
    ResolverOutput,
    SourceKind,
)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
STUDY_URL = "https://clinicaltrials.gov/study/"
PAGE_SIZE = 20

# Only what parse_study reads, which keeps responses (and the cache) small.
FIELDS = (
    "NCTId|BriefSummary|"
    "OverallStatus|WhyStopped|PrimaryCompletionDate|StudyFirstPostDate|LastUpdatePostDate|"
    "StudyType|Phase|EnrollmentCount|EnrollmentType|"
    "DesignAllocation|DesignInterventionModel|DesignMasking|"
    "PrimaryOutcomeMeasure|PrimaryOutcomeDescription|PrimaryOutcomeTimeFrame|"
    "LeadSponsorName|HasResults"
)

_STATUS_FIELDS = ("overallStatus", "whyStopped", "primaryCompletionDateStruct")
_DESIGN_FIELDS = ("studyType", "phases", "designInfo", "enrollmentInfo")


def parse_ct_date(value: str | None) -> date | None:
    """`YYYY-MM-DD`, or `YYYY-MM` read as the last day of the month.

    A partial date resolves to its latest possible day so that evidence is never shown to a
    run dated earlier than it may really be.
    """
    if not value:
        return None
    parts = [int(p) for p in value.split("-")]
    if len(parts) == 1:
        return date(parts[0], 12, 31)
    if len(parts) == 2:
        return date(parts[0], parts[1], calendar.monthrange(parts[0], parts[1])[1])
    return date(*parts)


def _fragment(source: dict, fields: tuple[str, ...]) -> str | None:
    picked = {name: source[name] for name in fields if name in source}
    return json.dumps(picked, ensure_ascii=False) if picked else None


def parse_study(study: dict, retrieved_at: datetime | None = None) -> list[Evidence]:
    """Evidence for one study record. Parts missing from the record are skipped."""
    retrieved_at = retrieved_at or datetime.now(UTC)
    protocol = study.get("protocolSection", {})
    nct = protocol["identificationModule"]["nctId"]
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})

    first_posted = parse_ct_date(status.get("studyFirstPostDateStruct", {}).get("date"))
    last_updated = parse_ct_date(status.get("lastUpdatePostDateStruct", {}).get("date"))
    sponsor = protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name")
    interventional = design.get("studyType") == "INTERVENTIONAL"

    items: list[Evidence] = []

    def add(
        part: str, excerpt: str | None, published_at: date | None, status_key: str | None = None
    ):
        if not excerpt:
            return
        items.append(
            Evidence(
                id=f"{nct}:{part}",  # placeholder, replaced when the bundle is frozen
                source="ClinicalTrials.gov",
                source_family="registry",
                source_kind=SourceKind.REGISTRY,
                url=STUDY_URL + nct,
                locator=Locator(type="nct", value=nct),
                excerpt=excerpt,
                published_at=published_at,
                retrieved_at=retrieved_at,
                level=(
                    EvidenceLevel.HUMAN_INTERVENTIONAL
                    if interventional
                    else EvidenceLevel.HUMAN_OBSERVATIONAL
                ),
                independence_group=sponsor_group(sponsor),
                status_key=status_key,
                version=1,
            )
        )

    add("summary", protocol.get("descriptionModule", {}).get("briefSummary"), first_posted)

    for number, outcome in enumerate(protocol.get("outcomesModule", {}).get("primaryOutcomes", [])):
        add(f"primary-outcome-{number + 1}", json.dumps(outcome, ensure_ascii=False), first_posted)

    add(
        "status",
        _fragment(status, _STATUS_FIELDS),
        last_updated,
        status_key=f"nct:{nct}:overall_status",
    )
    add("design", _fragment(design, _DESIGN_FIELDS), last_updated, status_key=f"nct:{nct}:design")
    return items


def build_queries(query: ResolverOutput, page_size: int = PAGE_SIZE) -> list[dict[str, str]]:
    """Search parameters: one query per known asset, else per target within the indication."""
    base = {"pageSize": str(page_size), "fields": FIELDS}
    if query.known_assets:
        return [{**base, "query.intr": asset} for asset in query.known_assets]
    return [
        {**base, "query.cond": query.indication.name, "query.term": target.symbol}
        for target in query.targets
    ]


class ClinicalTrialsConnector:
    """Satisfies `Connector`. Fetches only the first page of results for each query."""

    name = "clinicaltrials"

    def __init__(self, http: CachedHttpClient, page_size: int = PAGE_SIZE) -> None:
        self._http = http
        self._page_size = page_size

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        found: dict[str, tuple[dict, datetime]] = {}  # by NCT id: a study seen twice is read once
        for params in build_queries(query, self._page_size):
            response = await self._http.get(API_URL, params)
            for study in json.loads(response.body).get("studies", []):
                nct = study["protocolSection"]["identificationModule"]["nctId"]
                found.setdefault(nct, (study, response.fetched_at))

        evidence: list[Evidence] = []
        for nct in sorted(found):
            study, fetched_at = found[nct]
            evidence.extend(parse_study(study, retrieved_at=fetched_at))
        return filter_as_of(evidence, as_of)
