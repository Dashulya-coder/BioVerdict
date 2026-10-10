"""openFDA: what the FDA approved in the target's class, and what those labels say (A6).

An unapproved drug has no approval and no label. What exists is the regulatory record of the
approved drugs against the same target (the analogs Open Targets names), so for each of them this
connector reads:

1. Drugs@FDA: the original approval and every approved efficacy supplement (a new indication).
   Each is one status fact, dated by its approval day, so a replayed run sees only the approvals
   that had happened by its cutoff.
2. The current label: indications and the boxed warning as status facts, the clinical studies
   section as text a model picks quotes from.

Everything here describes an analog, never the asset: the `source` of every record says so, and
the source family is `regulatory_analog`. A label is the current text, dated by its effective
date; openFDA keeps no earlier versions, so a run replayed before that date does not see it.

Without a key openFDA allows 1,000 requests a day per address (`OPENFDA_API_KEY` raises it to
120,000). The key travels in a header, so it is never part of an address or of the cache.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import UTC, date, datetime

import httpx

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.opentargets import OpenTargetsApi
from bioverdict.connectors.pricing import analog_name, analogs_payload, parse_analogs, same_drug
from bioverdict.connectors.text import chunks
from bioverdict.resolver.names import normalize
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, ResolverOutput, SourceKind

log = logging.getLogger(__name__)

API_URL = "https://api.fda.gov/drug"
APPLICATION_URL = (
    "https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo="
)
LABEL_URL = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid="
ANALOG_FAMILY = "regulatory_analog"
MAX_APPLICATIONS = 5  # per analog; an innovator drug has one or two

APPROVED = "AP"
GENERIC = "ANDA"
ORIGINAL, EFFICACY = "ORIG", "Efficacy"
APPROVED_STAGE = "APPROVAL"  # Open Targets' name of the stage of an approved drug
# Label sections kept whole: short, and each is one statement of the regulator.
WHOLE_SECTIONS = {
    "indications_and_usage": EvidenceLevel.REGISTRY_RECORD,
    # A boxed warning rests on trials and on reports after approval: the weaker of the two.
    "boxed_warning": EvidenceLevel.HUMAN_OBSERVATIONAL,
}
TEXT_SECTION = "clinical_studies"


class OpenFdaError(ValueError):
    """openFDA answered with something that is not a result list."""


def require_results(body: bytes) -> None:
    """Refuse a body without a `results` list, so that an error page is never cached."""
    try:
        answer = json.loads(body)
    except ValueError as exc:
        raise OpenFdaError("the answer is not JSON") from exc
    if not isinstance(answer, dict) or not isinstance(answer.get("results"), list):
        raise OpenFdaError("the answer has no result list")


def _day(text: object) -> date | None:
    """openFDA writes days as 20210528."""
    try:
        return datetime.strptime(str(text), "%Y%m%d").replace(tzinfo=UTC).date()
    except ValueError:
        return None


def _names(record: dict, field: str) -> list[str]:
    return list((record.get("openfda") or {}).get(field) or [])


def _is_analog(record: dict, analog: str) -> bool:
    """A combination product or a drug that only shares a word with the analog is another drug."""
    return any(same_drug(name, analog) for name in _names(record, "generic_name"))


def _source(what: str, record: dict, analog: str) -> str:
    brand = ", ".join(_names(record, "brand_name")) or analog
    return f"FDA {what} of approved analog {brand} ({analog.lower()})"


def parse_approvals(answer: dict, analog: str, retrieved_at: datetime) -> list[Evidence]:
    """One record per approved original application and per approved efficacy supplement."""
    evidence = []
    for application in (answer.get("results") or [])[:MAX_APPLICATIONS]:
        number = application.get("application_number")
        # An ANDA is a generic copy of a drug that is already approved: not a new approval.
        if not number or number.startswith(GENERIC) or not _is_analog(application, analog):
            continue
        for submission in application.get("submissions") or []:
            kind = submission.get("submission_type")
            approved_on = _day(submission.get("submission_status_date"))
            wanted = (
                kind == ORIGINAL or submission.get("submission_class_code_description") == EFFICACY
            )
            if submission.get("submission_status") != APPROVED or not wanted or not approved_on:
                continue
            fragment = {
                "application_number": number,
                "sponsor_name": application.get("sponsor_name"),
                "brand_name": _names(application, "brand_name"),
                "generic_name": _names(application, "generic_name"),
                "route": _names(application, "route"),
            }
            fields = (
                "submission_type",
                "submission_number",
                "submission_status",
                "submission_status_date",
                "review_priority",
                "submission_class_code_description",
                "submission_property_type",
            )
            fragment |= {name: submission[name] for name in fields if submission.get(name)}
            key = f"fda:{number}:{kind}{submission.get('submission_number', '')}"
            evidence.append(
                Evidence(
                    id=key,  # placeholder until the freeze
                    source=_source("approval", application, analog),
                    source_family=ANALOG_FAMILY,
                    source_kind=SourceKind.REGULATOR,
                    url=APPLICATION_URL + re.sub(r"\D", "", number),
                    locator=Locator(type="fda_application", value=number),
                    excerpt=json.dumps(fragment, ensure_ascii=False),
                    published_at=approved_on,
                    retrieved_at=retrieved_at,
                    level=EvidenceLevel.REGISTRY_RECORD,
                    independence_group=f"fda:{number}",
                    status_key=key,
                    version=1,
                )
            )
    return evidence


def pick_label(answer: dict, analog: str, applications: set[str]) -> dict | None:
    """The newest label of the analog, preferring one filed under an approved application
    (a generic or a repackager publishes its own copy of the text)."""
    labels = [
        label
        for label in answer.get("results") or []
        if _is_analog(label, analog) and label.get("set_id") and _day(label.get("effective_time"))
    ]
    labels.sort(key=lambda label: str(label["effective_time"]), reverse=True)
    own = [label for label in labels if applications & set(_names(label, "application_number"))]
    return (own or labels or [None])[0]


def parse_label(
    label: dict,
    analog: str,
    retrieved_at: datetime,
    *,
    source: str | None = None,
    family: str = ANALOG_FAMILY,
    key_prefix: str = "fda-label",
    pieces: int | None = None,
) -> list[Evidence]:
    """The label's indications and boxed warning whole, its clinical studies in pieces.

    `pieces` keeps only the first pieces of the clinical studies; the keys carry `key_prefix` so
    that the same label read for another purpose is another record, not a replacement.
    """
    set_id = label["set_id"]
    shared = {
        "source": source or _source("label", label, analog),
        "source_family": family,
        "source_kind": SourceKind.REGULATOR,
        "url": LABEL_URL + set_id,
        "published_at": _day(label["effective_time"]),
        "retrieved_at": retrieved_at,
        "independence_group": f"fda-label:{set_id}",
        "version": 1,
    }
    evidence = []
    for section, level in WHOLE_SECTIONS.items():
        text = " ".join(label.get(section) or []).strip()
        if text:
            key = f"{key_prefix}:{set_id}:{section}"
            evidence.append(
                Evidence(
                    id=key,
                    locator=Locator(type="spl_set_id", value=f"{set_id}#{section}"),
                    excerpt=text,
                    level=level,
                    status_key=key,
                    **shared,
                )
            )
    studies = chunks(" ".join(label.get(TEXT_SECTION) or []))[:pieces]
    for number, piece in enumerate(studies, start=1):
        evidence.append(
            Evidence(
                id=f"{key_prefix}:{set_id}:{TEXT_SECTION}:{number}",
                locator=Locator(type="spl_set_id", value=f"{set_id}#{TEXT_SECTION}:{number}"),
                excerpt=piece,
                level=EvidenceLevel.HUMAN_INTERVENTIONAL,
                **shared,
            )
        )
    return evidence


class OpenFdaConnector:
    """Satisfies `Connector`. Needs an Ensembl id for the target; without one nothing is read.

    A request that fails does not hide the other analogs: it is listed in `problems`.
    """

    name = "openfda"

    def __init__(self, http: CachedHttpClient, api_key: str | None = None) -> None:
        self._http = http
        self._api = OpenTargetsApi(http)
        token = base64.b64encode(f"{api_key}:".encode()).decode() if api_key else None
        self._headers = {"Authorization": f"Basic {token}"} if token else None
        self.problems: list[str] = []

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        self.problems = []
        own = {normalize(name) for name in query.known_assets}
        own |= {normalize(asset.name) for asset in query.assets}
        analogs: dict[str, None] = {}  # each analog once, in the order the targets name them
        for target in query.targets:
            if target.ensembl is None:
                continue
            answer, fetched_at = await self._api.query(analogs_payload(target.ensembl))
            for item in parse_analogs(answer, fetched_at):
                if normalize(analog_name(item)) not in own:  # the asset is not its own analog
                    analogs.setdefault(analog_name(item))

        evidence: list[Evidence] = []
        for analog in analogs:
            approvals: list[Evidence] = []
            if (read := await self._read("drugsfda", analog)) is not None:
                approvals = parse_approvals(read[0], analog, read[1])
            evidence += approvals
            applications = {e.locator.value for e in approvals if e.locator is not None}
            if (read := await self._read("label", analog)) is not None:
                label = pick_label(read[0], analog, applications)
                if label is not None:
                    evidence += parse_label(label, analog, read[1])
        return filter_as_of(evidence, as_of)

    async def _read(
        self, dataset: str, analog: str, search: str | None = None
    ) -> tuple[dict, datetime] | None:
        """The decoded answer and its download time; None when nothing matched or it failed."""
        params = {
            "search": search or f'openfda.generic_name:"{analog}"',
            "limit": str(MAX_APPLICATIONS),
        }
        if dataset == "label":
            params["sort"] = "effective_time:desc"
        try:
            response = await self._http.get(
                f"{API_URL}/{dataset}.json", params, validate=require_results, headers=self._headers
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != httpx.codes.NOT_FOUND:  # 404: nothing matched
                log.warning("openFDA %s of %s: HTTP %s", dataset, analog, exc.response.status_code)
                self.problems.append(f"openFDA {dataset} of {analog} could not be read")
            return None
        except (httpx.HTTPError, OpenFdaError) as exc:
            log.warning("openFDA %s of %s not read: %s", dataset, analog, type(exc).__name__)
            self.problems.append(f"openFDA {dataset} of {analog} could not be read")
            return None
        return json.loads(response.body), response.fetched_at


# --- Drugs approved for the indication -----------------------------------------------------------

INDICATION_FAMILY = "approved_for_indication"
INDICATION_KEY = "fda-indication"
MAX_COMPETITORS = 12  # labels kept, the ones that name the indication earliest
STUDY_PIECES = 1  # of 6,000 characters of each label: the pivotal trial, which fits 3 prompts
_BRAND_APPLICATIONS = "(openfda.application_number:NDA* OR openfda.application_number:BLA*)"

DISEASE_DRUGS_QUERY = """
query ($id: String!) {
  disease(efoId: $id) {
    id name
    drugAndClinicalCandidates { rows { maxClinicalStage drug { id name } } }
  }
}
"""


def approved_for(answer: dict) -> list[str]:
    """The drugs Open Targets lists as approved *for this disease* (not for any disease), once each.

    A salt of a name already taken ("fingolimod hydrochloride" after "fingolimod") is the same
    drug; its label is found under the shorter name.
    """
    disease = (answer.get("data") or {}).get("disease") or {}
    rows = ((disease.get("drugAndClinicalCandidates") or {}).get("rows")) or []
    names = sorted(
        {
            row["drug"]["name"].casefold()
            for row in rows
            if row.get("drug") and row.get("maxClinicalStage") == APPROVED_STAGE
        }
    )
    chosen: list[str] = []
    for name in names:
        if not any(name.startswith(earlier + " ") for earlier in chosen):
            chosen.append(name)
    return chosen


def indication_position(label: dict, indication: str) -> int | None:
    """Where the indications section first names the indication: early means it is the drug's
    purpose, late means it is one item in a long list (a corticosteroid)."""
    text = " ".join(label.get("indications_and_usage") or []).casefold()
    at = text.find(indication.casefold())
    return at if at >= 0 else None


def parse_competitor(label: dict, indication: str, retrieved_at: datetime) -> list[Evidence]:
    """Records of one label of a drug approved for the indication."""
    brand = ", ".join(_names(label, "brand_name")) or "label"
    generic = ", ".join(_names(label, "generic_name")).casefold()
    return parse_label(
        label,
        generic,
        retrieved_at,
        source=f"FDA label of {brand} ({generic}), approved for {indication}",
        family=INDICATION_FAMILY,
        key_prefix=INDICATION_KEY,
        pieces=STUDY_PIECES,
    )


class OpenFdaIndication(OpenFdaConnector):
    """Satisfies `Connector`. The drugs approved for the indication, whatever their target.

    Open Targets lists what is approved for the disease; openFDA gives the current label of each
    drug's brand application whose indications name the disease. The competitors of a new drug
    are these, not the oncology drugs that share its target. A drug is kept for the place where
    its label first names the indication, so a corticosteroid that lists it among forty others
    ranks last. A disease with no identifier in Open Targets gives nothing.
    """

    name = "openfda_indication"

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        self.problems = []
        disease = query.indication.mondo_id or query.indication.efo_id
        indication = query.indication.name
        if disease is None:
            return []
        answer, _ = await self._api.query(
            {"query": DISEASE_DRUGS_QUERY, "variables": {"id": disease}}
        )
        own = {normalize(name) for name in query.known_assets}
        own |= {normalize(asset.name) for asset in query.assets}
        found: dict[str, tuple[int, str, dict, datetime]] = {}  # label id -> its rank and label
        for drug in approved_for(answer):
            if normalize(drug) in own:
                continue
            search = (
                f'openfda.generic_name:"{drug}" AND indications_and_usage:"{indication}" '
                f"AND {_BRAND_APPLICATIONS}"
            )
            if (read := await self._read("label", drug, search)) is None:
                continue
            for label in read[0].get("results") or []:
                at = indication_position(label, indication)
                if at is None or not label.get("set_id") or not _day(label.get("effective_time")):
                    continue
                if drug not in " ".join(_names(label, "generic_name")).casefold():
                    continue
                found.setdefault(label["set_id"], (at, drug, label, read[1]))
                break  # the newest label of the drug
        ranked = sorted(found.values(), key=lambda item: (item[0], item[1]))[:MAX_COMPETITORS]
        evidence: list[Evidence] = []
        for _, _, label, fetched_at in ranked:
            evidence += parse_competitor(label, indication, fetched_at)
        return filter_as_of(evidence, as_of)
