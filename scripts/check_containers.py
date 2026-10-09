"""Check the running containers end to end: API health, one fixture run, the page, CORS.

Start them first, then run this from the repository root (CI does the same):

    docker compose up -d --build --wait
    python3 scripts/check_containers.py

Needs no keys and no network beyond localhost: the run is answered from the image's fixtures.
Other addresses: `--api http://host:8000 --page http://host:8080`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

RUN_SECONDS = 30


def call(url: str, body: dict | None = None, headers: dict[str, str] | None = None) -> tuple:
    data = None if body is None else json.dumps(body).encode()
    method = "OPTIONS" if headers and "Access-Control-Request-Method" in headers else None
    sent = {"content-type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, data=data, headers=sent, method=method)
    with urllib.request.urlopen(request, timeout=10) as answer:
        return answer.read(), answer.headers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--page", default="http://localhost:8080")
    args = parser.parse_args()

    health = json.loads(call(f"{args.api}/health")[0])
    print(f"api: {health['status']}, mode {health['mode']}")

    run_id = json.loads(call(f"{args.api}/runs", {"asset": "divarasib"})[0])["run_id"]
    deadline = time.monotonic() + RUN_SECONDS
    while True:
        run = json.loads(call(f"{args.api}/runs/{run_id}")[0])
        if run["status"] != "running":
            break
        if time.monotonic() > deadline:
            print(f"run {run_id} is still running after {RUN_SECONDS} s", file=sys.stderr)
            return 1
        time.sleep(0.5)
    print(f"run {run_id}: {run['status']}, verdict {run['verdict']}")
    if run["status"] != "done" or not run["verdict"]:
        return 1

    page = call(args.page)[0]
    print(f"page: {len(page)} bytes")
    if b"<div id=" not in page:
        print("the page is not the workspace", file=sys.stderr)
        return 1

    # The browser asks this before its first request; without the header the page cannot run.
    preflight = {"Origin": args.page, "Access-Control-Request-Method": "POST"}
    allowed = call(f"{args.api}/runs", headers=preflight)[1].get("access-control-allow-origin")
    print(f"cors: the api allows {allowed}")
    return 0 if allowed == args.page else 1


if __name__ == "__main__":
    sys.exit(main())
