"""Record real answers of the market sources for the connector tests (A9).

Run from the backend directory when a query changes:

    uv run python ../scripts/record_market_fixtures.py

It asks each source once and stores the raw answers in fixtures/raw/market/. The Orphanet file
(16 MB) and the cancer report are cut down to the records the tests read; nothing is rewritten.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from bioverdict.connectors.epidemiology import (
    CANCER_URL,
    CDC_URL,
    ORPHANET_URL,
    WORLD_BANK_URL,
    cancer_params,
    cdc_params,
    xrefs_payload,
)
from bioverdict.connectors.opentargets import API_URL
from bioverdict.connectors.pricing import CMS_API, PROGRAMS, analogs_payload

OUT = Path(__file__).parents[1] / "fixtures" / "raw" / "market"
KRAS, HAE = "ENSG00000133703", "MONDO_0019623"
ORPHA_CODES = {"91378", "72"}  # hereditary angioedema, Angelman syndrome


def save(name: str, body: bytes | str) -> None:
    data = body.encode("utf-8") if isinstance(body, str) else body
    (OUT / name).write_bytes(data)
    print(f"{name}: {len(data)} bytes")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        save("opentargets_analogs_kras.json", client.post(API_URL, json=analogs_payload(KRAS)).content)
        save("opentargets_xrefs_hae.json", client.post(API_URL, json=xrefs_payload(HAE)).content)
        for drug in ("SOTORASIB", "ADAGRASIB"):
            for program, dataset in PROGRAMS.items():
                answer = client.get(f"{CMS_API}/{dataset}/data", params={"keyword": drug, "size": "50"})
                save(f"cms_{program.split()[-1].lower()}_{drug.lower()}.json", answer.content)
        question = "Obesity among adults"
        save("cdc_obesity.json", client.get(CDC_URL, params=cdc_params(question)).content)
        for indicator in ("SP.POP.TOTL", "SP.POP.1564.TO", "SP.POP.65UP.TO"):
            answer = client.get(WORLD_BANK_URL + indicator, params={"format": "json", "mrnev": "1"})
            save(f"worldbank_{indicator}.json", answer.content)
        report = client.get(CANCER_URL, params=cancer_params("047")).text
        lines = report.splitlines()
        first_state = next(n for n, line in enumerate(lines) if line.startswith('"US (SEER+NPCR)'))
        save("cancer_lung.csv", "\n".join(lines[: first_state + 3]) + "\n")  # header, US, 2 states

        root = ET.fromstring(client.get(ORPHANET_URL).content)
        disorders = root.find("DisorderList")
        assert disorders is not None
        for disorder in list(disorders):
            if disorder.findtext("OrphaCode") not in ORPHA_CODES:
                disorders.remove(disorder)
        disorders.set("count", str(len(disorders)))
        save("orphanet_prevalence.xml", ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(json.dumps(sorted(p.name for p in OUT.iterdir()), indent=1))


if __name__ == "__main__":
    main()
