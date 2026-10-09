"""Record real PubMed Central full-text answers for the connector tests (A6).

Run from the backend directory when the connector reads other sections:

    uv run python ../scripts/record_pmc_fixtures.py

One paper under CC BY 4.0 is stored (PMID 38052910, Nature Medicine 2024,
doi:10.1038/s41591-023-02696-8), cut down to its front matter and the sections the connector
reads, and the first bytes of the service's answer for a paper it does not hold. Papers under a
non-commercial or no-derivatives licence are not recorded: the repository must not copy them.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from bioverdict.connectors.pmc import BIOC_URL, READ_SECTIONS

OUT = Path(__file__).parents[1] / "fixtures" / "raw" / "pmc"
OPEN_PAPER, ABSENT_PAPER = "38052910", "37611121"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60) as client:
        answer = client.get(f"{BIOC_URL}/{OPEN_PAPER}/unicode").raise_for_status().json()
        document = answer[0]["documents"][0]
        front, *rest = document["passages"]
        kept = [front, *(p for p in rest if p["infons"].get("section_type") in READ_SECTIONS)]
        for passage in kept:
            for field in ("annotations", "relations", "sentences"):
                passage.pop(field, None)
            passage["infons"] = {
                key: value for key, value in passage["infons"].items() if not key.startswith("name_")
            }
        document["passages"] = kept
        (OUT / f"bioc_{OPEN_PAPER}.json").write_text(
            json.dumps(answer, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        absent = client.get(f"{BIOC_URL}/{ABSENT_PAPER}/unicode").raise_for_status().content
        (OUT / "bioc_not_found.txt").write_bytes(absent[:160])
    for path in sorted(OUT.iterdir()):
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
