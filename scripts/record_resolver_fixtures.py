"""Record real Open Targets answers for the resolver tests.

Run from the backend directory when a resolver query changes or a case is added:

    uv run python ../scripts/record_resolver_fixtures.py

It performs the lookups listed below against the live API and stores every request/answer pair in
fixtures/raw/opentargets/resolver_recording.json, keyed by a hash of the request payload. The
tests replay that file, so they need no network and fail loudly if a query changed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
from pathlib import Path

import httpx

from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.opentargets import OpenTargetsApi
from bioverdict.resolver.lookup import OpenTargetsLookup
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate

DRUGS = [
    "divarasib", "divarasib adipate", "SAR444656", "HRO761", "STAR-0215", "ION582",
    "sonelokimab", "retatrutide", "RMC-9805", "elisrasib", "MariTide",
]  # fmt: skip
TARGETS = ["KRAS", "KRAS2", "WRN", "GLP1R", "KLKB1", "IRAK4", "CRLF2", "NOTAGENE"]
DISEASES = [
    "NSCLC", "obesity", "Alzheimer's disease", "hypertension", "multiple sclerosis",
    "MSI-high solid tumors", "hidradenitis suppurativa",
]  # fmt: skip

OUT = Path(__file__).parents[1] / "fixtures" / "raw" / "opentargets" / "resolver_recording.json"


def payload_key(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


async def main() -> None:
    recorded: dict[str, dict] = {}

    async def capture(response: httpx.Response) -> None:
        await response.aread()
        payload = json.loads(response.request.content)
        recorded[payload_key(payload)] = {"payload": payload, "answer": response.json()}

    conn = connect(Path(tempfile.mkdtemp()) / "record.db")
    migrate(conn)
    async with httpx.AsyncClient(timeout=30, event_hooks={"response": [capture]}) as client:
        lookup = OpenTargetsLookup(OpenTargetsApi(CachedHttpClient(client, HttpCache(conn))))
        for name in DRUGS:
            await lookup.find_drug(name)
        for symbol in TARGETS:
            await lookup.find_target(symbol)
        for name in DISEASES:
            await lookup.find_disease(name)

    OUT.write_text(
        json.dumps(recorded, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"recorded {len(recorded)} request/answer pairs to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
