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

from bioverdict.store.models import Evidence, EvidenceLevel, Locator, SourceKind

STUDY_URL = "https://clinicaltrials.gov/study/"

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
                independence_group=f"sponsor:{sponsor or 'unknown'}",
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
