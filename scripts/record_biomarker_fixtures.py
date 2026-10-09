"""Record real cBioPortal answers for the biomarker frequency tests (A9).

Run from the backend directory when the connector asks other questions:

    uv run python ../scripts/record_biomarker_fixtures.py

Stored in fixtures/raw/biomarker/: the gene and the study records whole; the cohort's sample
table and KRAS mutation table cut to one cancer type and to the fields the connector reads (the
whole tables are 3 MB and 1 MB). Rows are kept as served; no value is rewritten. The cohort is
the public MSK-IMPACT Clinical Sequencing Cohort (Zehir et al., Nat Med 2017).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from bioverdict.connectors.biomarker import API_URL, HEADERS, STUDY

OUT = Path(__file__).parents[1] / "fixtures" / "raw" / "biomarker"
GENE, CANCER_TYPE = "KRAS", "Non-Small Cell Lung Cancer"


def save(name: str, data: object) -> None:
    (OUT / name).write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=180, headers=HEADERS, base_url=API_URL) as client:
        gene = client.get(f"/genes/{GENE}").raise_for_status().json()
        save("gene_kras.json", gene)
        save("study.json", client.get(f"/studies/{STUDY}").raise_for_status().json())
        params = {
            "clinicalDataType": "SAMPLE",
            "attributeId": "CANCER_TYPE",
            "projection": "SUMMARY",
            "pageSize": "50000",
        }
        rows = client.get(f"/studies/{STUDY}/clinical-data", params=params).raise_for_status().json()
        samples = [
            {key: row[key] for key in ("sampleId", "patientId", "value")}
            for row in rows
            if row["value"] == CANCER_TYPE
        ]
        save("samples_nsclc.json", samples)
        kept = {sample["sampleId"] for sample in samples}
        body = {"entrezGeneIds": [gene["entrezGeneId"]], "sampleListId": f"{STUDY}_all"}
        path = f"/molecular-profiles/{STUDY}_mutations/mutations/fetch"
        answer = client.post(path, params={"projection": "SUMMARY"}, json=body).raise_for_status()
        save(
            "mutations_kras_nsclc.json",
            [
                {key: row[key] for key in ("sampleId", "patientId", "proteinChange")}
                for row in answer.json()
                if row["sampleId"] in kept
            ],
        )
    for path in sorted(OUT.iterdir()):
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
