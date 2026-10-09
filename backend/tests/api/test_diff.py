"""Comparing two finished runs, and recomputing a run on added evidence, through the API."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bioverdict import settings
from bioverdict.api.main import create_app
from bioverdict.api.schemas import DiffResponse
from bioverdict.llm import FakeLLM
from bioverdict.store.runs_repo import create_run

FIXTURES = Path(__file__).parents[3] / "fixtures"
LATER = {"E-0003", "E-0005", "E-0006", "E-0014", "E-0015"}  # absent as of 2026-06-30
ADDED = {
    "text": "The exploratory analysis reported no new safety signals at the recommended dose.",
    "url": "https://www.example.org/reports/divarasib-safety",
    "source": "Example congress abstract",
    "source_kind": "company",
    "level": "human_interventional",
    "published_at": "2026-09-01",
}


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "api.sqlite"


# The stand-in model finds the added document bearing on nothing in the report.
NOTHING_TO_PLACE = {"links": [], "new_claims": [], "unmatched": []}


@pytest.fixture
def client(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("USE_FIXTURES", "1")
    drafts = json.loads((FIXTURES / "reasoning" / "divarasib.json").read_text(encoding="utf-8"))
    return TestClient(
        create_app(
            db_path,
            FIXTURES,
            llm=lambda _: FakeLLM({**drafts, "reasoning.classify": NOTHING_TO_PLACE}),
        )
    )


def start(client: TestClient, as_of: str) -> str:
    return client.post("/runs", json={"asset": "divarasib", "as_of": as_of}).json()["run_id"]


def diff(client: TestClient, head: str, base: str) -> DiffResponse:
    response = client.get(f"/runs/{head}/diff", params={"against": base})
    assert response.status_code == 200
    return DiffResponse.model_validate(response.json())


def test_two_cutoffs_differ_by_the_evidence_published_between_them(client: TestClient) -> None:
    early, late = start(client, "2026-06-30"), start(client, "2026-10-07")

    result = diff(client, late, early)

    assert (result.base.run_id, result.head.run_id) == (early, late)
    assert (result.base.evidence_count, result.head.evidence_count) == (10, 15)
    assert {e.id for e in result.evidence_added} == LATER and result.evidence_removed == []
    added = [c for c in result.claims if c.change == "added"]
    assert added and all(set(c.new_evidence_ids) <= LATER and c.new_evidence_ids for c in added)
    assert result.head.confidence != result.base.confidence and not result.verdict_changed


def test_the_comparison_reads_the_other_way_round(client: TestClient) -> None:
    early, late = start(client, "2026-06-30"), start(client, "2026-10-07")

    result = diff(client, early, late)

    assert {e.id for e in result.evidence_removed} == LATER and result.evidence_added == []
    removed = [c for c in result.claims if c.change == "removed"]
    assert removed and all(c.after is None and c.new_evidence_ids == [] for c in removed)


def test_a_run_does_not_differ_from_itself(client: TestClient) -> None:
    run_id = start(client, "2026-10-07")

    result = diff(client, run_id, run_id)

    claims = sum(len(s["claims"]) for s in client.get(f"/runs/{run_id}/report").json()["sections"])
    assert result.claims == [] and result.gates == [] and result.chain == []
    assert result.evidence_added == [] and result.unchanged_claims == claims


def test_a_changed_claim_shows_its_footing_before_and_after(client: TestClient) -> None:
    early, late = start(client, "2026-06-30"), start(client, "2026-10-07")

    changed = [c for c in diff(client, late, early).claims if c.change == "changed"]

    assert changed and all(c.before is not None and c.after is not None for c in changed)
    assert all(c.before.confidence != c.after.confidence for c in changed if c.before and c.after)


def test_added_evidence_starts_a_new_run_that_is_compared_with_its_original(
    client: TestClient,
) -> None:
    original = start(client, "2026-10-07")

    response = client.post(f"/runs/{original}/evidence", json={"evidence": [ADDED]})

    assert response.status_code == 202
    new = response.json()["run_id"]
    summary = client.get(f"/runs/{new}").json()
    assert new != original and summary["status"] == "done"
    assert summary["input"]["parent_run_id"] == original
    result = DiffResponse.model_validate(client.get(f"/runs/{new}/diff").json())
    assert (result.base.run_id, result.base.bundle_version, result.head.bundle_version) == (
        original,
        1,
        2,
    )
    (added,) = result.evidence_added
    assert (added.excerpt, added.source_family) == (ADDED["text"], "analyst_added")
    assert added.claim_ids == []  # the stand-in model does not know the new document


def test_a_fixture_api_does_not_pretend_to_reason_over_new_evidence(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USE_FIXTURES", "1")
    client = TestClient(create_app(db_path, FIXTURES))
    original = start(client, "2026-10-07")

    response = client.post(f"/runs/{original}/evidence", json={"evidence": [ADDED]})

    assert response.status_code == 422 and "live API" in response.json()["detail"]
    assert len(client.get("/runs").json()) == 1


def test_a_live_api_without_a_model_key_refuses_added_evidence(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USE_FIXTURES", "1")
    client = TestClient(create_app(db_path, FIXTURES))
    original = start(client, "2026-10-07")
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.post(f"/runs/{original}/evidence", json={"evidence": [ADDED]})

    assert response.status_code == 503 and "ANTHROPIC_API_KEY" in response.json()["detail"]


@pytest.mark.parametrize(
    "change",
    [
        {"text": "too short"},
        {"url": "ftp://example.org/x"},
        {"level": "strongest"},
        {"source_kind": "blog"},
    ],
)
def test_malformed_evidence_is_rejected(client: TestClient, change: dict) -> None:
    original = start(client, "2026-10-07")

    response = client.post(f"/runs/{original}/evidence", json={"evidence": [ADDED | change]})

    assert response.status_code == 422 and len(client.get("/runs").json()) == 1


def test_evidence_that_adds_nothing_or_is_too_late_is_refused(client: TestClient) -> None:
    original = start(client, "2026-06-30")

    late = client.post(f"/runs/{original}/evidence", json={"evidence": [ADDED]})
    twice = client.post(
        f"/runs/{original}/evidence", json={"evidence": [ADDED, ADDED], "as_of": "2026-10-07"}
    )

    assert late.status_code == 422 and "after the cutoff" in late.json()["detail"]
    assert twice.status_code == 422 and "repeat each other" in twice.json()["detail"]
    assert len(client.get("/runs").json()) == 1


def test_unknown_unfinished_and_unnamed_comparisons(client: TestClient, db_path: Path) -> None:
    run_id = start(client, "2026-10-07")
    with settings.open_database(db_path) as conn:
        create_run(conn, "R-going", {"asset": "divarasib"}, settings.today())

    assert client.get(f"/runs/{run_id}/diff").status_code == 422  # nothing to compare with
    assert client.get(f"/runs/{run_id}/diff", params={"against": "R-nope"}).status_code == 404
    assert client.get("/runs/R-nope/diff", params={"against": run_id}).status_code == 404
    assert client.get(f"/runs/{run_id}/diff", params={"against": "R-going"}).status_code == 409
    assert client.post("/runs/R-nope/evidence", json={"evidence": [ADDED]}).status_code == 404
    assert client.post("/runs/R-going/evidence", json={"evidence": [ADDED]}).status_code == 422
