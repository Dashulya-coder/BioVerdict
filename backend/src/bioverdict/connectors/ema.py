"""EMA: which medicines the European Union has authorised, from the Agency's open data.

The European Medicines Agency publishes one JSON file of every human medicine it has assessed:
its status (authorised, refused, withdrawn, suspended), the opinion and authorisation dates, the
holder, the therapeutic area and the approved indication. The file is the register itself, not a
page about it, so each medicine is one status fact: nothing here is read by a model.

Two kinds of record are kept:

- the asset's own, when its name is the medicine's active substance: whether it is authorised in
  the Union, whatever the phase the registries show (family `registry`);
- the competitors: authorised, non-generic medicines whose approved indication names the
  indication of the question (family `approved_for_indication`, beside the FDA labels).

A record is dated by its last update, because the file shows today's status; a run replayed to an
earlier day does not see a decision that was revised after it. The file is about 7 MB and is
cached like any answer.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.validate import BodyError, _decoded
from bioverdict.resolver.names import normalize
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import Evidence, EvidenceLevel, Locator, ResolverOutput, SourceKind

DATA_URL = (
    "https://www.ema.europa.eu/en/documents/report/medicines-output-medicines_json-report_en.json"
)
OWN_FAMILY = "registry"
COMPETITOR_FAMILY = "approved_for_indication"
MAX_COMPETITORS = 12
MAX_POSITION = 400  # the indication named later than this is one item in a long list
AUTHORISED = "Authorised"
KEPT_FIELDS = (
    "name_of_medicine",
    "ema_product_number",
    "medicine_status",
    "opinion_status",
    "international_non_proprietary_name_common_name",
    "active_substance",
    "therapeutic_area_mesh",
    "therapeutic_indication",
    "marketing_authorisation_developer_applicant_holder",
    "opinion_adopted_date",
    "european_commission_decision_date",
    "marketing_authorisation_date",
    "refusal_of_marketing_authorisation_date",
    "withdrawal_of_application_date",
    "withdrawal_expiry_revocation_lapse_of_marketing_authorisation_date",
    "suspension_of_marketing_authorisation_date",
    "conditional_approval",
    "additional_monitoring",
    "orphan_medicine",
    "medicine_url",
)
_DATES = (
    "last_updated_date",
    "marketing_authorisation_date",
    "opinion_adopted_date",
    "refusal_of_marketing_authorisation_date",
)


def require_medicines(body: bytes) -> None:
    """Refuse a body that is not the register: an object with a list of medicines in `data`."""
    answer = _decoded(body)
    if not isinstance(answer, dict) or not isinstance(answer.get("data"), list):
        raise BodyError("the answer has no list of medicines")


def _day(text: object) -> date | None:
    """The Agency writes days as 19/06/2026."""
    try:
        return datetime.strptime(str(text), "%d/%m/%Y").replace(tzinfo=UTC).date()
    except ValueError:
        return None


def _substances(record: dict) -> set[str]:
    names = {
        record.get("international_non_proprietary_name_common_name"),
        record.get("active_substance"),
    }
    return {normalize(name) for name in names if name}


def _evidence(record: dict, family: str, retrieved_at: datetime) -> Evidence | None:
    number = record.get("ema_product_number")
    if not number:
        return None
    published = next((d for key in _DATES if (d := _day(record.get(key)))), None)
    fragment = {key: record[key] for key in KEPT_FIELDS if record.get(key)}
    name = record.get("name_of_medicine") or number
    substance = record.get("international_non_proprietary_name_common_name") or ""
    return Evidence(
        id=f"ema:{number}",  # placeholder until the freeze
        source=f"EMA medicine record: {name} ({substance.casefold()})",
        source_family=family,
        source_kind=SourceKind.REGULATOR,
        url=record.get("medicine_url") or DATA_URL,
        locator=Locator(type="ema_product", value=number),
        excerpt=json.dumps(fragment, ensure_ascii=False),
        published_at=published,
        retrieved_at=retrieved_at,
        level=EvidenceLevel.REGISTRY_RECORD,
        independence_group=f"ema:{number}",
        status_key=f"ema:{number}",
        version=1,
    )


def select(rows: list[dict], query: ResolverOutput) -> list[tuple[dict, str]]:
    """The asset's own medicines, then the competitors, each with the family it goes under."""
    own = {normalize(name) for name in query.known_assets}
    own |= {normalize(asset.name) for asset in query.assets}
    indication = query.indication.name.casefold().strip()
    chosen: list[tuple[dict, str]] = []
    competitors: list[dict] = []
    for record in rows:
        if record.get("category") != "Human":
            continue
        if own & _substances(record):
            chosen.append((record, OWN_FAMILY))
        elif (
            indication
            and indication != "not specified"
            and record.get("medicine_status") == AUTHORISED
            and record.get("generic") != "Yes"
            and record.get("biosimilar") != "Yes"
            and 0
            <= (record.get("therapeutic_indication") or "").casefold().find(indication)
            < MAX_POSITION
        ):
            competitors.append(record)
    competitors.sort(
        key=lambda r: (
            _day(r.get("marketing_authorisation_date")) or date.min,
            r["ema_product_number"],
        ),
        reverse=True,
    )
    return chosen + [(record, COMPETITOR_FAMILY) for record in competitors[:MAX_COMPETITORS]]


class EmaConnector:
    """Satisfies `Connector`. A question that names no asset and no indication gives nothing."""

    name = "ema_medicines"

    def __init__(self, http: CachedHttpClient) -> None:
        self._http = http
        self.problems: list[str] = []

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        self.problems = []
        response = await self._http.get(DATA_URL, validate=require_medicines)
        rows = [r for r in json.loads(response.body)["data"] if isinstance(r, dict)]
        evidence = [
            item
            for record, family in select(rows, query)
            if (item := _evidence(record, family, response.fetched_at)) is not None
        ]
        return filter_as_of(evidence, as_of)
