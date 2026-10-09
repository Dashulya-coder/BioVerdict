"""Record real SEC EDGAR answers for the connector tests (A10).

Run from the backend directory, with the contact the SEC asks for:

    SEC_USER_AGENT="Name email" uv run python ../scripts/record_edgar_fixtures.py

Stored in fixtures/raw/edgar/: the company list cut to a few companies; one company's filing
list cut to its newest 8-Ks and a few other forms; the index of one 8-K and the first part of
its press-release exhibit. SEC filings are public records; no value is rewritten.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from bioverdict.connectors.edgar import ARCHIVE_URL, COMPANIES_URL, SUBMISSIONS_URL

OUT = Path(__file__).parents[1] / "fixtures" / "raw" / "edgar"
CIK = 1628171  # Revolution Medicines, Inc.
ACCESSION = "0001193125-26-335039"  # 8-K of 2026-08-05, items 2.02 and 9.01
EXHIBIT = "rvmd-ex99_1.htm"
KEPT_COMPANIES = {1628171, 1114448, 318154}  # Revolution Medicines, Novartis, Amgen
EVENT_ROWS, OTHER_ROWS = 10, 5
EXHIBIT_BYTES = 40_000  # the business update; the financial tables that follow are not read


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    folder = ACCESSION.replace("-", "")
    with httpx.Client(timeout=60, headers={"User-Agent": os.environ["SEC_USER_AGENT"]}) as client:

        def get(url: str) -> httpx.Response:
            time.sleep(0.3)  # well under the SEC's ten requests a second
            return client.get(url).raise_for_status()

        companies = get(COMPANIES_URL).json()
        kept = {k: v for k, v in companies.items() if v["cik_str"] in KEPT_COMPANIES}
        (OUT / "company_tickers.json").write_text(json.dumps(kept, indent=1) + "\n")
        answer = get(SUBMISSIONS_URL.format(cik=CIK)).json()
        recent = answer["filings"]["recent"]
        forms = recent["form"]
        events = [n for n, form in enumerate(forms) if form == "8-K"][:EVENT_ROWS]
        others = [n for n, form in enumerate(forms) if form != "8-K"][:OTHER_ROWS]
        rows = sorted(events + others)
        submissions = {
            "cik": answer["cik"],
            "name": answer["name"],
            "filings": {"recent": {key: [values[n] for n in rows] for key, values in recent.items()}},
        }
        (OUT / "submissions.json").write_text(json.dumps(submissions, indent=1) + "\n")
        for name, limit in (("index.json", None), (EXHIBIT, EXHIBIT_BYTES)):
            body = get(ARCHIVE_URL.format(cik=CIK, folder=folder, name=name)).content
            (OUT / name).write_bytes(body[:limit])
    for path in sorted(OUT.iterdir()):
        print(f"{path.name}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
