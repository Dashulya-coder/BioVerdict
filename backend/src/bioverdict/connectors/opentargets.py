"""Open Targets Platform (GraphQL): target-disease evidence and drug clinical stage.

Two kinds of evidence come out of it:
- a drug's clinical stage (`registry_record`: it says where a program stands, not what it found);
- one record per data type of a target-disease association, graded by what the data type is.

Records are snapshots of the current release and carry no publication date. Each has a
`status_key`, so a later snapshot replaces an earlier one, and the evidence is only visible to a
run whose `as_of` is not before the day it was downloaded (see `store.as_of`).
"""

from __future__ import annotations

import json
from datetime import datetime

from bioverdict.store.models import Evidence, EvidenceLevel, Locator, SourceKind

API_URL = "https://api.platform.opentargets.org/api/v4/graphql"
SITE_URL = "https://platform.opentargets.org"

SEARCH_QUERY = """
query ($name: String!) {
  search(queryString: $name, entityNames: ["drug"], page: {index: 0, size: 5}) {
    hits { id name entity }
  }
}
"""
DRUG_QUERY = """
query ($id: String!) {
  drug(chemblId: $id) {
    id name maximumClinicalStage
    indications { rows { maxClinicalStage disease { id name } } }
  }
}
"""
ASSOCIATION_QUERY = """
query ($disease: String!, $target: String!) {
  disease(efoId: $disease) {
    id name
    associatedTargets(Bs: [$target]) {
      rows { score target { id approvedSymbol } datatypeScores { id score } }
    }
  }
}
"""

# How strong a kind of evidence is for the claim "this target matters in this disease".
# Anything not listed is skipped rather than guessed. `literature` is text mining of papers,
# which the PubMed connector covers with the papers themselves.
DATATYPE_LEVEL: dict[str, EvidenceLevel] = {
    "genetic_association": EvidenceLevel.HUMAN_GENETICS,
    "somatic_mutation": EvidenceLevel.HUMAN_OBSERVATIONAL,
    "rna_expression": EvidenceLevel.HUMAN_OBSERVATIONAL,
    "animal_model": EvidenceLevel.ANIMAL_IN_VIVO,
    "affected_pathway": EvidenceLevel.IN_VITRO,
    "clinical": EvidenceLevel.REGISTRY_RECORD,
    "known_drug": EvidenceLevel.REGISTRY_RECORD,
}


def search_payload(name: str) -> dict:
    return {"query": SEARCH_QUERY, "variables": {"name": name}}


def drug_payload(chembl_id: str) -> dict:
    return {"query": DRUG_QUERY, "variables": {"id": chembl_id}}


def association_payload(disease_id: str, ensembl_id: str) -> dict:
    return {"query": ASSOCIATION_QUERY, "variables": {"disease": disease_id, "target": ensembl_id}}


def pick_drug(search_response: dict, name: str) -> str | None:
    """The ChEMBL id of the hit named exactly `name` (ignoring case), never a similar one.

    "divarasib adipate" is a different record from "divarasib"; similar names are told apart by
    id, not by string similarity (docs/domain-pack-oncology.md).
    """
    wanted = name.strip().casefold()
    for hit in search_response["data"]["search"]["hits"]:
        if hit.get("entity") == "drug" and hit["name"].casefold() == wanted:
            return hit["id"]
    return None


def _evidence(
    part: str,
    url: str,
    locator: Locator,
    excerpt: str,
    level: EvidenceLevel,
    group: str,
    status_key: str,
    retrieved_at: datetime,
) -> Evidence:
    return Evidence(
        id=f"ot:{part}",  # placeholder, replaced when the bundle is frozen
        source="Open Targets",
        source_family="target_database",
        source_kind=SourceKind.REGISTRY,
        url=url,
        locator=locator,
        excerpt=excerpt,
        published_at=None,
        retrieved_at=retrieved_at,
        level=level,
        independence_group=group,
        status_key=status_key,
        version=1,
    )


def parse_drug(
    drug_response: dict, retrieved_at: datetime, disease_id: str | None = None
) -> list[Evidence]:
    """The drug's clinical stage, with its stage in `disease_id` when the drug has one there."""
    drug = (drug_response.get("data") or {}).get("drug")
    if not drug:
        return []
    fragment = {
        "id": drug["id"],
        "name": drug["name"],
        "maximumClinicalStage": drug["maximumClinicalStage"],
    }
    rows = ((drug.get("indications") or {}).get("rows")) or []
    for row in rows:
        if disease_id is not None and row["disease"]["id"] == disease_id:
            fragment["indication"] = row
    return [
        _evidence(
            f"{drug['id']}:clinical_stage",
            f"{SITE_URL}/drug/{drug['id']}",
            Locator(type="chembl", value=drug["id"]),
            json.dumps(fragment, ensure_ascii=False),
            EvidenceLevel.REGISTRY_RECORD,
            "database:opentargets-clinical",
            f"chembl:{drug['id']}:clinical_stage",
            retrieved_at,
        )
    ]


def parse_associations(association_response: dict, retrieved_at: datetime) -> list[Evidence]:
    """One evidence per data type of the association between the target and the disease."""
    disease = (association_response.get("data") or {}).get("disease")
    if not disease:  # an unknown or retired disease id answers null, not an error
        return []
    items: list[Evidence] = []
    for row in disease["associatedTargets"]["rows"]:
        target, ensembl = row["target"]["approvedSymbol"], row["target"]["id"]
        for datatype in sorted(row["datatypeScores"], key=lambda d: d["id"]):
            level = DATATYPE_LEVEL.get(datatype["id"])
            if level is None:
                continue
            fragment = {
                "target": target,
                "disease": disease["id"],
                "datatype": datatype["id"],
                "score": datatype["score"],
            }
            items.append(
                _evidence(
                    f"{ensembl}:{disease['id']}:{datatype['id']}",
                    f"{SITE_URL}/evidence/{ensembl}/{disease['id']}",
                    Locator(type="ensembl", value=ensembl),
                    json.dumps(fragment, ensure_ascii=False),
                    level,
                    f"database:opentargets-{datatype['id']}",
                    f"ot:{ensembl}:{disease['id']}:{datatype['id']}",
                    retrieved_at,
                )
            )
    return items
