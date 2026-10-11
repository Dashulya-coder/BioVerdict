"""ClinicalTrials.gov v2: turns study records and posted results into Evidence.

Per study the search record yields the brief summary, each primary outcome, the status (with the
reason a trial was stopped, when given) and the design. That is `registry_record` evidence: it
shows that a study exists and how it is set up, not what it found, so it proves no efficacy.

What a study found is read separately, for studies that have posted results: each outcome measure
(primary first) becomes a `human_interventional` evidence with its group values, confidence
intervals and statistical analyses. That is what the kill criterion K1 (the same target failed in
this indication) and the probability of success need.

Structured parts are stored as a JSON fragment of the API response, so a quote can be an exact
substring of the excerpt. Status, design and results can be amended by the sponsor, so they carry
a `status_key` and a newer record replaces an older one. The public API has no record history, so
a status or result can only be as recent as its last posting: for an earlier `as_of` it is filtered
out rather than guessed.

Besides the studies the user's drug or target points at, the search also asks for stopped studies
(terminated, withdrawn, suspended) of the same target and indication: the failed analogs that K1
looks for rarely rank among the first results of a plain search.
"""

from __future__ import annotations

import calendar
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.sponsors import sponsor_group
from bioverdict.connectors.validate import BodyError, json_object
from bioverdict.store.as_of import filter_as_of
from bioverdict.store.models import (
    Evidence,
    EvidenceLevel,
    Locator,
    ResolverOutput,
    SourceKind,
)

log = logging.getLogger(__name__)

API_URL = "https://clinicaltrials.gov/api/v2/studies"
STUDY_URL = "https://clinicaltrials.gov/study/"
PAGE_SIZE = 20
MAX_PAGES = 2  # of each query: a drug has a handful of studies, a target many
MAX_RESULT_STUDIES = 10  # studies whose posted results are read, per fetch
MAX_MEASURES = 6  # outcome measures kept per study, primary ones first
STOPPED = "TERMINATED|WITHDRAWN|SUSPENDED"

# Only what parse_study reads, which keeps responses (and the cache) small.
FIELDS = (
    "NCTId|BriefSummary|"
    "OverallStatus|WhyStopped|PrimaryCompletionDate|StudyFirstPostDate|LastUpdatePostDate|"
    "StudyType|Phase|EnrollmentCount|EnrollmentType|"
    "DesignAllocation|DesignInterventionModel|DesignMasking|"
    "PrimaryOutcomeMeasure|PrimaryOutcomeDescription|PrimaryOutcomeTimeFrame|"
    "LeadSponsorName|HasResults|"
    "ArmGroupLabel|ArmGroupType|InterventionName|InterventionType|InterventionArmGroupLabel"
)

# Only what parse_results reads. The results of a study can run to 70 KB; this is under 5.
RESULT_FIELDS = (
    "NCTId|ResultsFirstPostDate|LastUpdatePostDate|"
    "OutcomeMeasureType|OutcomeMeasureTitle|OutcomeMeasureParamType|OutcomeMeasureDispersionType|"
    "OutcomeMeasureUnitOfMeasure|OutcomeMeasureTimeFrame|"
    "OutcomeGroupId|OutcomeGroupTitle|OutcomeClassTitle|OutcomeCategoryTitle|"
    "OutcomeMeasurementGroupId|OutcomeMeasurementValue|OutcomeMeasurementLowerLimit|OutcomeMeasurementUpperLimit|"
    "OutcomeMeasurementSpread|"
    "OutcomeAnalysisStatisticalMethod|OutcomeAnalysisParamType|OutcomeAnalysisParamValue|"
    "OutcomeAnalysisCIPctValue|OutcomeAnalysisCILowerLimit|OutcomeAnalysisCIUpperLimit|"
    "OutcomeAnalysisPValue|OutcomeAnalysisGroupId"
)

_STATUS_FIELDS = ("overallStatus", "whyStopped", "primaryCompletionDateStruct")
_DESIGN_FIELDS = ("studyType", "phases", "designInfo", "enrollmentInfo")
_MEASUREMENT_FIELDS = ("groupId", "value", "lowerLimit", "upperLimit", "spread")
_ANALYSIS_FIELDS = (
    "groupIds",
    "statisticalMethod",
    "paramType",
    "paramValue",
    "ciPctValue",
    "ciLowerLimit",
    "ciUpperLimit",
    "pValue",
)


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


def _sponsor(study: dict) -> str | None:
    protocol = study.get("protocolSection", {})
    return protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name")


def _evidence(
    nct: str,
    part: str,
    excerpt: str | None,
    published_at: date | None,
    level: EvidenceLevel,
    sponsor: str | None,
    retrieved_at: datetime,
    status_key: str | None = None,
    independence_group: str | None = None,
) -> Evidence | None:
    if not excerpt:
        return None
    return Evidence(
        id=f"{nct}:{part}",  # placeholder, replaced when the bundle is frozen
        source="ClinicalTrials.gov",
        source_family="registry",
        source_kind=SourceKind.REGISTRY,
        url=STUDY_URL + nct,
        locator=Locator(type="nct", value=nct),
        excerpt=excerpt,
        published_at=published_at,
        retrieved_at=retrieved_at,
        level=level,
        independence_group=independence_group or sponsor_group(sponsor),
        status_key=status_key,
        version=1,
    )


def parse_study(study: dict, retrieved_at: datetime | None = None) -> list[Evidence]:
    """Registry evidence for one study record. Parts missing from the record are skipped."""
    retrieved_at = retrieved_at or datetime.now(UTC)
    protocol = study.get("protocolSection", {})
    nct = protocol["identificationModule"]["nctId"]
    status = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    # Keep the intervention-to-arm mapping with the design. This identifies experimental
    # drugs without inferring a name from a title or accidentally selecting a comparator.
    design = {name: design[name] for name in _DESIGN_FIELDS if name in design}
    arms = protocol.get("armsInterventionsModule", {})
    for name, fields in (
        ("armGroups", ("label", "type")),
        ("interventions", ("name", "type", "armGroupLabels")),
    ):
        if arms.get(name):
            design[name] = [{k: row[k] for k in fields if k in row} for row in arms[name]]

    first_posted = parse_ct_date(status.get("studyFirstPostDateStruct", {}).get("date"))
    last_updated = parse_ct_date(status.get("lastUpdatePostDateStruct", {}).get("date"))
    # The registry serves the current text of a record, not its history. A summary or an
    # endpoint may have been rewritten at any update, so it is dated by the last one: dating it
    # by the first posting would show today's wording to a run replayed years earlier.
    described = last_updated or first_posted
    sponsor = _sponsor(study)
    record = EvidenceLevel.REGISTRY_RECORD

    parts = [
        _evidence(
            nct,
            "summary",
            protocol.get("descriptionModule", {}).get("briefSummary"),
            described,
            record,
            sponsor,
            retrieved_at,
        )
    ]
    for number, outcome in enumerate(protocol.get("outcomesModule", {}).get("primaryOutcomes", [])):
        text = json.dumps(outcome, ensure_ascii=False)
        parts.append(
            _evidence(
                nct,
                f"primary-outcome-{number + 1}",
                text,
                described,
                record,
                sponsor,
                retrieved_at,
            )
        )
    parts.append(
        _evidence(
            nct,
            "status",
            _fragment(status, _STATUS_FIELDS),
            last_updated,
            record,
            sponsor,
            retrieved_at,
            status_key=f"nct:{nct}:overall_status",
        )
    )
    parts.append(
        _evidence(
            nct,
            "design",
            json.dumps(design, ensure_ascii=False) if design else None,
            last_updated,
            record,
            sponsor,
            retrieved_at,
            status_key=f"nct:{nct}:design",
        )
    )
    return [part for part in parts if part is not None]


def _outcome_fragment(measure: dict) -> dict:
    """One outcome measure with its values, intervals and analyses, empty parts left out."""
    classes = []
    for outcome_class in measure.get("classes", []):
        categories = []
        for category in outcome_class.get("categories", []):
            measurements = [
                {name: item[name] for name in _MEASUREMENT_FIELDS if name in item}
                for item in category.get("measurements", [])
            ]
            categories.append(
                {"title": category.get("title"), "measurements": measurements}
                if category.get("title")
                else {"measurements": measurements}
            )
        classes.append(
            {"title": outcome_class["title"], "categories": categories}
            if outcome_class.get("title")
            else {"categories": categories}
        )
    fragment = {
        "type": measure.get("type"),
        "title": measure.get("title"),
        "paramType": measure.get("paramType"),
        "dispersionType": measure.get("dispersionType"),
        "unitOfMeasure": measure.get("unitOfMeasure"),
        "timeFrame": measure.get("timeFrame"),
        "groups": [
            {key: group[key] for key in ("id", "title") if key in group}
            for group in measure.get("groups", [])
        ],
        "classes": classes,
        "analyses": [
            {name: analysis[name] for name in _ANALYSIS_FIELDS if name in analysis}
            for analysis in measure.get("analyses", [])
        ],
    }
    return {key: value for key, value in fragment.items() if value not in (None, [], "")}


RESULT_HEAD = "Outcome measure ("  # how a result record's text begins


def result_lines(record: dict) -> str:
    """An outcome measure as lines of text: a heading, then every value next to its group.

    Stored as JSON, the values carried group codes ("OG001") and stood after the headings, so a
    quote could name the endpoint or a group but never tie a value to its group, and the judge
    removed such claims as "the quote only names the endpoint" (docs/eval.md, section 9). As
    lines, a quote such as "Tolebrutinib 60 mg: 0.530 (range 0.439 to 0.641)" is verbatim.
    """
    # A value is named only by its own group id: the registry's order of values need not follow
    # the order of the groups, and a record read before ids were kept has none to go by.
    names = {
        g["id"]: g.get("title", "")
        for g in record.get("groups", [])
        if isinstance(g, dict) and g.get("id")
    }
    head = [str(record[k]) for k in ("type", "title") if record.get(k)]
    lines = [f"{RESULT_HEAD}{'; '.join(head)})"]
    if not names and record.get("groups"):
        titles = ", ".join(str(g.get("title")) for g in record["groups"] if isinstance(g, dict))
        lines.append(f"Groups (the record does not say which value is whose): {titles}")
    for key, label in (
        ("paramType", "reported as"),
        ("dispersionType", "spread is"),
        ("unitOfMeasure", "unit"),
        ("timeFrame", "time frame"),
    ):
        if record.get(key):
            lines[0] += f"; {label}: {record[key]}"
    for outcome_class in record.get("classes", []):
        for category in outcome_class.get("categories", []):
            label = " / ".join(
                str(t) for t in (outcome_class.get("title"), category.get("title")) if t
            )
            for item in category.get("measurements", []):
                group = names.get(item.get("groupId"), item.get("groupId")) or "unnamed group"
                value = f"{group}: {item.get('value')}"
                if item.get("lowerLimit") is not None:
                    value += f" (range {item['lowerLimit']} to {item.get('upperLimit')})"
                if item.get("spread") is not None:
                    value += f" (spread {item['spread']})"
                lines.append(f"{label}: {value}" if label else value)
    for analysis in record.get("analyses", []):
        who = ", ".join(str(names.get(g, g)) for g in analysis.get("groupIds", []))
        parts = [
            f"{key} {analysis[key]}"
            for key in ("statisticalMethod", "paramType", "paramValue", "pValue")
            if analysis.get(key) is not None
        ]
        if analysis.get("ciLowerLimit") is not None:
            ci = f"{analysis['ciPctValue']}% CI" if analysis.get("ciPctValue") else "CI"
            parts.append(f"{ci} {analysis['ciLowerLimit']} to {analysis.get('ciUpperLimit')}")
        lines.append(f"Analysis of {who or 'the groups'}: " + ", ".join(parts))
    return "\n".join(lines)


def parse_results(
    results: dict, study: dict, retrieved_at: datetime | None = None
) -> list[Evidence]:
    """What a study found: one `human_interventional` evidence per outcome measure.

    `results` is the answer to a request for `RESULT_FIELDS`; `study` is the search record the
    sponsor comes from. Primary measures come first and at most `MAX_MEASURES` are kept.
    """
    retrieved_at = retrieved_at or datetime.now(UTC)
    nct = study["protocolSection"]["identificationModule"]["nctId"]
    status = results.get("protocolSection", {}).get("statusModule", {})
    posted = parse_ct_date(status.get("resultsFirstPostDateStruct", {}).get("date"))
    search_status = study.get("protocolSection", {}).get("statusModule", {})
    updated = parse_ct_date(status.get("lastUpdatePostDateStruct", {}).get("date"))
    updated = updated or parse_ct_date(
        search_status.get("lastUpdatePostDateStruct", {}).get("date")
    )
    # The API returns today's result text, including amendments. Its first posting date
    # cannot establish that today's values were already public then.
    posted = max(d for d in (posted, updated or retrieved_at.date()) if d is not None)
    measures = (
        results.get("resultsSection", {})
        .get("outcomeMeasuresModule", {})
        .get("outcomeMeasures", [])
    )
    measures = sorted(measures, key=lambda m: m.get("type") != "PRIMARY")[:MAX_MEASURES]

    evidence = []
    for number, measure in enumerate(measures, start=1):
        item = _evidence(
            nct,
            f"result-{number}",
            result_lines(_outcome_fragment(measure)),
            posted,
            EvidenceLevel.HUMAN_INTERVENTIONAL,
            _sponsor(study),
            retrieved_at,
            status_key=f"nct:{nct}:result:{measure.get('type', 'OTHER').lower()}:{number}",
            # What a trial found is one dataset: the registry and the papers about it count once.
            independence_group=f"trial:{nct}",
        )
        if item is not None:
            evidence.append(item)
    return evidence


NO_INDICATION = "not specified"  # what the Resolver writes when the input names no disease


def _asset_condition(query: ResolverOutput) -> str | None:
    """The indication an asset's studies are limited to, or None when the input named none."""
    name = query.indication.name.strip()
    return name if name and name != NO_INDICATION else None


def build_queries(
    query: ResolverOutput, page_size: int = PAGE_SIZE, in_indication: bool = True
) -> list[dict[str, str]]:
    """Search parameters.

    One query per known asset, else one per target within the indication; each is repeated
    restricted to stopped studies, because failed analogs rarely rank first.

    An asset is searched within the run's indication too: a drug is studied in several diseases,
    and its trials in another one (evobrutinib in rheumatoid arthritis, for a question about
    multiple sclerosis) are not evidence for this question. `in_indication=False` drops that
    limit, for an asset that has no study registered for the indication.
    """
    base = {"pageSize": str(page_size), "fields": FIELDS}
    if query.known_assets:
        condition = _asset_condition(query) if in_indication else None
        scope = {"query.cond": condition} if condition else {}
        searches = [{**base, "query.intr": asset, **scope} for asset in query.known_assets]
    else:
        searches = [
            {**base, "query.cond": query.indication.name, "query.term": target.symbol}
            for target in query.targets
        ]
    stopped = [{**search, "filter.overallStatus": STOPPED} for search in searches]
    return searches + stopped


_SEARCH_PAGE = json_object("studies")
_STUDY = json_object()  # a study without posted results answers `{}`


class ClinicalTrialsConnector:
    """Satisfies `Connector`. Reads up to `MAX_PAGES` pages of each query and posted results.

    A search that fails raises, since nothing can be said without it. The results of one study
    that cannot be read do not stop the rest: the study is listed in `problems`, so the caller
    can report that its results are missing rather than absent.
    """

    name = "clinicaltrials"

    def __init__(
        self, http: CachedHttpClient, page_size: int = PAGE_SIZE, max_pages: int = MAX_PAGES
    ) -> None:
        self._http = http
        self._page_size = page_size
        self._max_pages = max_pages
        self.problems: list[str] = []  # what the last fetch could not read

    async def _pages(self, params: dict[str, str]) -> AsyncIterator[tuple[dict, datetime]]:
        """The studies of a query, page after page, with the time each page was downloaded."""
        token: str | None = None
        for _ in range(self._max_pages):
            page_params = {**params, "pageToken": token} if token else params
            response = await self._http.get(API_URL, page_params, validate=_SEARCH_PAGE)
            body = json.loads(response.body)
            for study in body.get("studies", []):
                yield study, response.fetched_at
            token = body.get("nextPageToken")
            if not token:
                return
        if token:
            self.problems.append(f"search truncated after {self._max_pages} page(s)")

    async def _search(self, queries: list[dict[str, str]]) -> dict[str, tuple[dict, datetime]]:
        """The studies the queries find, by NCT id: a study seen twice is read once."""
        found: dict[str, tuple[dict, datetime]] = {}
        for params in queries:
            async for study, fetched_at in self._pages(params):
                nct = study["protocolSection"]["identificationModule"]["nctId"]
                found.setdefault(nct, (study, fetched_at))
        return found

    async def fetch(self, query: ResolverOutput, as_of: date) -> list[Evidence]:
        self.problems = []
        found = await self._search(build_queries(query, self._page_size))
        if not found and query.known_assets and _asset_condition(query):
            # Better the drug's studies elsewhere, said to be elsewhere, than no registry record.
            found = await self._search(build_queries(query, self._page_size, in_indication=False))
            if found:
                self.problems.append(
                    f"no study of {', '.join(query.known_assets)} is registered for "
                    f"{query.indication.name}: its studies in other indications are listed instead"
                )

        evidence: list[Evidence] = []
        for nct in sorted(found):
            study, fetched_at = found[nct]
            evidence.extend(parse_study(study, retrieved_at=fetched_at))

        with_results = [nct for nct in sorted(found) if found[nct][0].get("hasResults")]
        if len(with_results) > MAX_RESULT_STUDIES:
            self.problems.append(
                f"results of {len(with_results) - MAX_RESULT_STUDIES} study/studies omitted by limit"
            )
        for nct in with_results[:MAX_RESULT_STUDIES]:
            try:
                response = await self._http.get(
                    f"{API_URL}/{nct}", {"fields": RESULT_FIELDS}, validate=_STUDY
                )
            except (httpx.HTTPError, BodyError) as exc:
                log.warning("results of %s not read: %s", nct, exc)
                self.problems.append(f"results of {nct} could not be read ({type(exc).__name__})")
                continue
            study = found[nct][0]
            result = json.loads(response.body)
            measures = (
                result.get("resultsSection", {})
                .get("outcomeMeasuresModule", {})
                .get("outcomeMeasures", [])
            )
            if len(measures) > MAX_MEASURES:
                self.problems.append(f"outcomes of {nct} truncated to {MAX_MEASURES} measures")
            evidence.extend(parse_results(result, study, retrieved_at=response.fetched_at))
        return filter_as_of(evidence, as_of)
