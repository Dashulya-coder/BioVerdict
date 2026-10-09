"""Record real openFDA answers for the connector tests (A6).

Run from the backend directory when a query changes:

    uv run python ../scripts/record_openfda_fixtures.py

It asks openFDA once for each analog and stores the answers in fixtures/raw/openfda/. A label is
cut down to the fields the connector reads (a whole label is over 100 kB); no value is rewritten.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from bioverdict.connectors.openfda import API_URL, MAX_APPLICATIONS, TEXT_SECTION, WHOLE_SECTIONS

OUT = Path(__file__).parents[1] / "fixtures" / "raw" / "openfda"
ANALOGS = ("SOTORASIB", "ADAGRASIB", "LECANEMAB")  # two KRAS drugs; a biologic with a boxed warning
LABEL_FIELDS = ("set_id", "effective_time", "version", "openfda", TEXT_SECTION, *WHOLE_SECTIONS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=60) as client:
        for analog in ANALOGS:
            params = {"search": f'openfda.generic_name:"{analog}"', "limit": str(MAX_APPLICATIONS)}
            approvals = client.get(f"{API_URL}/drugsfda.json", params=params).raise_for_status()
            (OUT / f"drugsfda_{analog.lower()}.json").write_bytes(approvals.content)
            params["sort"] = "effective_time:desc"
            answer = client.get(f"{API_URL}/label.json", params=params).raise_for_status().json()
            answer["results"] = [
                {name: label[name] for name in LABEL_FIELDS if name in label}
                for label in answer["results"]
            ]
            (OUT / f"label_{analog.lower()}.json").write_text(
                json.dumps(answer, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )
    for path in sorted(OUT.iterdir()):
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
