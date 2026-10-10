"""Finding drug, target and disease identifiers in Open Targets (A1).

Identifiers always come from the API, never from a model. A name is accepted only through the
rules in `names.py`; when nothing matches, or several unrelated things do, the result carries the
candidates and no choice, so the caller can say so in `assumptions`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bioverdict.connectors.opentargets import OpenTargetsApi
from bioverdict.resolver.names import (
    Candidate,
    MatchKind,
    choose,
    match_kind,
    normalize,
    rank_candidates,
)

SEARCH_QUERY = """
query ($name: String!, $entity: String!, $size: Int!) {
  search(queryString: $name, entityNames: [$entity], page: {index: 0, size: $size}) {
    hits { id name }
  }
}
"""
DRUGS_QUERY = """
query ($ids: [String!]!) {
  drugs(chemblIds: $ids) {
    id name drugType maximumClinicalStage
    synonyms { label }
    parentMolecule { id }
    childMolecules { id }
  }
}
"""
INDICATIONS_QUERY = """
query ($id: String!) {
  drug(chemblId: $id) {
    indications { rows { maxClinicalStage disease { id name } } }
  }
}
"""
STAGE_ORDER = ("UNKNOWN", "PRECLINICAL", "PHASE_1", "PHASE_2", "PHASE_3", "PHASE_4", "APPROVAL")
TARGETS_QUERY = """
query ($ids: [String!]!) {
  targets(ensemblIds: $ids) {
    id approvedSymbol
    synonyms { label }
    proteinIds { id source }
  }
}
"""
DISEASES_QUERY = """
query ($ids: [String!]!) {
  diseases(efoIds: $ids) {
    id name
    synonyms { terms }
    parents { id }
  }
}
"""

SEARCH_SIZE = 10  # a disease can sit below subtypes and measurements in the ranking


def search_payload(name: str, entity: str, size: int = SEARCH_SIZE) -> dict:
    return {"query": SEARCH_QUERY, "variables": {"name": name, "entity": entity, "size": size}}


def details_payload(query: str, ids: list[str]) -> dict:
    return {"query": query, "variables": {"ids": ids}}


@dataclass(frozen=True)
class DrugResolution:
    chosen: Candidate | None
    drug_type: str | None = None
    matched: tuple[Candidate, ...] = ()  # every candidate that really matched
    rejected: tuple[str, ...] = ()  # names the search returned that do not match the query


@dataclass(frozen=True)
class TargetMatch:
    symbol: str
    ensembl: str
    uniprot: str | None


@dataclass(frozen=True)
class DiseaseMatch:
    id: str
    name: str
    kind: MatchKind


@dataclass(frozen=True)
class DrugIndication:
    disease_id: str
    name: str
    stage: str  # Open Targets' maxClinicalStage, for example PHASE_3


@dataclass(frozen=True)
class DiseaseResolution:
    chosen: DiseaseMatch | None
    candidates: tuple[DiseaseMatch, ...] = field(default=())  # every acceptable match


def _parent_links(records: list[dict]) -> dict[str, str]:
    """Which record is the parent of which, read from both sides of the relation.

    Open Targets lists a salt under its parent's `childMolecules`, or the parent under the
    salt's `parentMolecule`, and does not always do both.
    """
    parent_of: dict[str, str] = {}
    for drug in records:
        parent = drug.get("parentMolecule")
        if parent:
            parent_of[drug["id"]] = parent["id"]
        for child in drug.get("childMolecules") or []:
            parent_of[child["id"]] = drug["id"]
    return parent_of


def _swissprot(target: dict) -> str | None:
    return next((p["id"] for p in target["proteinIds"] if p["source"] == "uniprot_swissprot"), None)


class OpenTargetsLookup:
    def __init__(self, api: OpenTargetsApi) -> None:
        self._api = api

    async def _hits(self, name: str, entity: str) -> list[str]:
        answer, _ = await self._api.query(search_payload(name, entity))
        return [hit["id"] for hit in answer["data"]["search"]["hits"]]

    async def find_drug(self, name: str) -> DrugResolution:
        ids = await self._hits(name, "drug")
        if not ids:
            return DrugResolution(None)
        answer, _ = await self._api.query(details_payload(DRUGS_QUERY, ids))
        records = [d for d in answer["data"]["drugs"] if d]
        parent_of = _parent_links(records)
        candidates = [
            Candidate(
                chembl_id=d["id"],
                name=d["name"],
                synonyms=tuple(s["label"] for s in d["synonyms"]),
                parent_id=parent_of.get(d["id"]),
            )
            for d in records
        ]
        ranked = rank_candidates(name, candidates)
        chosen = choose(ranked)
        drug_type = next(
            (d["drugType"] for d in records if chosen and d["id"] == chosen.chembl_id), None
        )
        if chosen is not None and chosen.parent_id is not None:
            # A salt was named: its parent is the drug the development data are recorded against.
            parent = await self._fetch_candidate(chosen.parent_id)
            if parent is not None:
                chosen, drug_type = parent
        matched = {r.candidate.chembl_id for r in ranked}
        return DrugResolution(
            chosen=chosen,
            drug_type=drug_type,
            matched=tuple(r.candidate for r in ranked),
            rejected=tuple(c.name for c in candidates if c.chembl_id not in matched),
        )

    async def _fetch_candidate(self, chembl_id: str) -> tuple[Candidate, str | None] | None:
        answer, _ = await self._api.query(details_payload(DRUGS_QUERY, [chembl_id]))
        records = [d for d in answer["data"]["drugs"] if d]
        if not records:
            return None
        drug = records[0]
        candidate = Candidate(
            chembl_id=drug["id"],
            name=drug["name"],
            synonyms=tuple(s["label"] for s in drug["synonyms"]),
        )
        return candidate, drug["drugType"]

    async def drug_indications(self, chembl_id: str) -> list[DrugIndication]:
        """The diseases Open Targets lists for a drug, the most advanced stage first.

        Equal stages keep Open Targets' order, so the answer is the same on every run.
        """
        answer, _ = await self._api.query(
            {"query": INDICATIONS_QUERY, "variables": {"id": chembl_id}}
        )
        drug = answer["data"]["drug"] or {}
        rows = (drug.get("indications") or {}).get("rows") or []
        found = [
            DrugIndication(r["disease"]["id"], r["disease"]["name"], r["maxClinicalStage"])
            for r in rows
            if r.get("disease")
        ]

        def rank(item: DrugIndication) -> int:
            return STAGE_ORDER.index(item.stage) if item.stage in STAGE_ORDER else 0

        return sorted(found, key=rank, reverse=True)

    async def find_target(self, symbol: str) -> TargetMatch | None:
        """The target whose approved symbol is `symbol`, else the only one listing it as a synonym."""
        ids = await self._hits(symbol, "target")
        if not ids:
            return None
        answer, _ = await self._api.query(details_payload(TARGETS_QUERY, ids))
        targets = [t for t in answer["data"]["targets"] if t]
        wanted = normalize(symbol)
        by_symbol = [t for t in targets if normalize(t["approvedSymbol"]) == wanted]
        by_synonym = [
            t for t in targets if wanted in {normalize(s["label"]) for s in t["synonyms"]}
        ]
        found = by_symbol or (by_synonym if len(by_synonym) == 1 else [])
        proteins = {_swissprot(t) for t in found}
        if len(found) > 1 and len(proteins) == 1 and None not in proteins:
            # One gene in the pseudoautosomal region is listed once per sex chromosome (CRLF2:
            # an X and a Y record, same protein). The older record, the X copy, is the one the
            # disease evidence is filed under.
            found = [min(found, key=lambda t: t["id"])]
        if len(found) != 1:
            return None
        target = found[0]
        return TargetMatch(target["approvedSymbol"], target["id"], _swissprot(target))

    async def find_disease(self, name: str) -> DiseaseResolution:
        """A MONDO disease by name or synonym. Other term types by their exact name, or by a
        synonym when the disease's own subtypes hang under them.

        Open Targets also holds measurements and traits that list a disease name as a synonym;
        those are not the disease. One exception is real: release 26.09 files multiple sclerosis
        under 'multiple sclerosis symptom measurement' (EFO_0803536), which is the parent of the
        relapsing and progressive forms and carries the disease's evidence. A term like that is
        accepted when a MONDO disease among the hits names it as its parent.
        """
        ids = await self._hits(name, "disease")
        if not ids:
            return DiseaseResolution(None)
        answer, _ = await self._api.query(details_payload(DISEASES_QUERY, ids))
        diseases = [d for d in answer["data"]["diseases"] if d]
        parents_of_diseases = {
            parent["id"]
            for d in diseases
            if d["id"].startswith("MONDO_")
            for parent in d.get("parents") or []
        }
        matches: list[DiseaseMatch] = []
        for disease in diseases:
            terms = [term for entry in disease["synonyms"] for term in entry["terms"]]
            kind = match_kind(name, disease["name"], terms)
            is_mondo = disease["id"].startswith("MONDO_")
            holds_subtypes = disease["id"] in parents_of_diseases
            if kind is MatchKind.NAME or (kind is not None and (is_mondo or holds_subtypes)):
                matches.append(DiseaseMatch(disease["id"], disease["name"], kind))

        def strength(match: DiseaseMatch) -> tuple[MatchKind, bool]:
            """Name beats synonym; within that a MONDO term beats any other."""
            return (match.kind, not match.id.startswith("MONDO_"))

        matches.sort(key=lambda m: (*strength(m), m.name, m.id))
        best = [m for m in matches if strength(m) == strength(matches[0])] if matches else []
        chosen = best[0] if len(best) == 1 else None  # several equally good: ambiguous
        return DiseaseResolution(chosen, tuple(matches))
