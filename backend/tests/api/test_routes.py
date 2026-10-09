import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bioverdict import settings
from bioverdict.api.main import create_app
from bioverdict.api.schemas import (
    ClaimView,
    EvidenceView,
    MarketResponse,
    ReportResponse,
    TraceResponse,
)
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.store.models import ResolverOutput
from bioverdict.store.runs_repo import create_run

FIXTURES = Path(__file__).parents[3] / "fixtures"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "api.sqlite"


@pytest.fixture
def client(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("USE_FIXTURES", "1")
    return TestClient(create_app(db_path, FIXTURES))


def start(client: TestClient) -> str:
    response = client.post("/runs", json={"asset": "divarasib"})
    assert response.status_code == 202
    return response.json()["run_id"]


def test_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "mode": "fixtures"}


def test_health_tells_a_client_when_runs_are_live(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USE_FIXTURES", "0")
    assert client.get("/health").json()["mode"] == "live"


def test_starting_a_run_returns_its_id_at_once(client: TestClient) -> None:
    body = client.post("/runs", json={"asset": "divarasib"}).json()

    assert body["status"] == "running" and body["run_id"].startswith("R-")


def test_the_run_finishes_and_is_listed(client: TestClient) -> None:
    run_id = start(client)

    summary = client.get(f"/runs/{run_id}").json()
    assert summary["status"] == "done" and summary["verdict"] == "Conditional"
    assert summary["as_of"] == settings.today().isoformat()
    assert [r["run_id"] for r in client.get("/runs").json()] == [run_id]


def test_the_as_of_date_of_a_run_can_be_chosen(client: TestClient) -> None:
    response = client.post("/runs", json={"asset": "divarasib", "as_of": "2026-06-30"})
    assert client.get(f"/runs/{response.json()['run_id']}").json()["as_of"] == "2026-06-30"


def test_the_report_has_the_documented_shape(client: TestClient) -> None:
    run_id = start(client)

    response = client.get(f"/runs/{run_id}/report")

    assert response.status_code == 200
    report = ReportResponse.model_validate(response.json())
    assert report.executive.verdict.value == "Conditional"
    assert [link.link.value for link in report.translation_chain] == [
        "molecular_effect",
        "human_exposure",
        "target_engagement",
        "biological_response",
        "patient_benefit",
    ]


def test_a_claim_and_its_evidence_can_be_drilled_into(client: TestClient) -> None:
    run_id = start(client)
    report = client.get(f"/runs/{run_id}/report").json()
    claim = next(c for s in report["sections"] for c in s["claims"] if c["links"])
    evidence_id = claim["links"][0]["evidence_id"]

    claim_response = client.get(f"/runs/{run_id}/claims/{claim['id']}")
    evidence_response = client.get(f"/runs/{run_id}/evidence/{evidence_id}")

    assert ClaimView.model_validate(claim_response.json()).id == claim["id"]
    evidence = EvidenceView.model_validate(evidence_response.json())
    assert claim["id"] in evidence.claim_ids and claim["links"][0]["quote"] in evidence.excerpt


def test_the_resolved_input_of_a_run_is_served(client: TestClient) -> None:
    run_id = start(client)

    resolved = ResolverOutput.model_validate(client.get(f"/runs/{run_id}/resolver").json())

    assert resolved.targets[0].symbol == "KRAS" and resolved.assumptions


def test_the_whole_bundle_is_listed_not_only_what_the_report_cites(client: TestClient) -> None:
    run_id = start(client)

    listed = [EvidenceView.model_validate(e) for e in client.get(f"/runs/{run_id}/evidence").json()]
    cited = client.get(f"/runs/{run_id}/report").json()["sources"]

    assert len(listed) == 15 and len(cited) < len(listed)
    assert [e.id for e in listed] == sorted(e.id for e in listed)
    assert any(e.claim_ids for e in listed) and any(not e.claim_ids for e in listed)


def test_a_cutoff_limits_the_listed_evidence(client: TestClient) -> None:
    run_id = client.post("/runs", json={"asset": "divarasib", "as_of": "2026-06-30"}).json()[
        "run_id"
    ]
    assert len(client.get(f"/runs/{run_id}/evidence").json()) == 10


def test_resolver_and_evidence_are_not_ready_before_their_steps(
    client: TestClient, db_path: Path
) -> None:
    with settings.open_database(db_path) as conn:
        create_run(conn, "R-waiting", {"asset": "divarasib"}, settings.today())

    assert client.get("/runs/R-waiting/resolver").status_code == 409
    assert client.get("/runs/R-waiting/evidence").status_code == 409
    assert client.get("/runs/R-nope/resolver").status_code == 404
    assert client.get("/runs/R-nope/evidence").status_code == 404


def test_the_market_of_a_run_without_market_records_says_what_is_missing(
    client: TestClient,
) -> None:
    run_id = start(client)

    market = MarketResponse.model_validate(client.get(f"/runs/{run_id}/market").json())

    assert market.label == "modeled" and market.tam_usd is None and market.sources == []
    assert "not percentiles" in market.range_basis
    assert [reason.split(":")[0] for reason in market.missing] == ["patients", "price"]


def test_the_market_is_not_ready_before_the_bundle_and_unknown_runs_are_404(
    client: TestClient, db_path: Path
) -> None:
    with settings.open_database(db_path) as conn:
        create_run(conn, "R-waiting", {"asset": "divarasib"}, settings.today())

    assert client.get("/runs/R-waiting/market").status_code == 409
    assert client.get("/runs/R-nope/market").status_code == 404


def test_the_trace_lists_the_steps(client: TestClient) -> None:
    run_id = start(client)

    trace = TraceResponse.model_validate(client.get(f"/runs/{run_id}/trace").json())

    assert [e.step for e in trace.events if e.status == "done"][-1] == "run"


def test_an_unknown_asset_is_refused_with_the_list_of_known_ones(client: TestClient) -> None:
    response = client.post("/runs", json={"asset": "no-such-drug"})

    assert response.status_code == 422 and "divarasib" in response.json()["detail"]
    assert client.get("/runs").json() == []  # no run was created


def test_a_run_without_an_asset_is_refused(client: TestClient) -> None:
    response = client.post(
        "/runs", json={"indication": "NSCLC", "mechanism": "KRAS G12C inhibitor"}
    )
    assert response.status_code == 422


def test_a_live_run_without_a_model_key_is_refused_before_it_starts(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    response = client.post("/runs", json={"asset": "divarasib"})

    assert response.status_code == 503 and "ANTHROPIC_API_KEY" in response.json()["detail"]
    assert client.get("/runs").json() == []  # no run was created, and no fixture answered


def live_client(db_path: Path, monkeypatch: pytest.MonkeyPatch, asked: list[str]) -> TestClient:
    """The API in live mode, with the fixture run standing in for the sources and the model."""
    monkeypatch.setenv("USE_FIXTURES", "0")

    def stand_in(conn, run_id, text):
        asked.append(text)
        return run_fixture(conn, run_id, "divarasib", FIXTURES)

    return TestClient(create_app(db_path, FIXTURES, live=stand_in))


@pytest.mark.parametrize(
    "body,text",
    [
        ({"asset": " GDC-6036 "}, "GDC-6036"),
        (
            {"indication": "NSCLC", "mechanism": "KRAS G12C inhibitor"},
            "KRAS G12C inhibitor for NSCLC",
        ),
    ],
)
def test_a_live_run_takes_any_asset_or_an_indication_with_a_mechanism(
    db_path: Path, monkeypatch: pytest.MonkeyPatch, body: dict, text: str
) -> None:
    asked: list[str] = []
    client = live_client(db_path, monkeypatch, asked)

    run_id = client.post("/runs", json=body).json()["run_id"]

    assert asked == [text]
    assert client.get(f"/runs/{run_id}").json()["status"] == "done"
    assert client.get(f"/runs/{run_id}/report").status_code == 200


def test_a_live_run_about_nothing_is_refused(
    db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []
    client = live_client(db_path, monkeypatch, asked)

    assert client.post("/runs", json={"asset": "  "}).status_code == 422
    assert asked == [] and client.get("/runs").json() == []


def test_unknown_runs_and_items_are_404(client: TestClient) -> None:
    run_id = start(client)

    assert client.get("/runs/R-nope").status_code == 404
    assert client.get("/runs/R-nope/report").status_code == 404
    assert client.get("/runs/R-nope/trace").status_code == 404
    assert client.get(f"/runs/{run_id}/claims/C-9999").status_code == 404
    assert client.get(f"/runs/{run_id}/evidence/E-9999").status_code == 404


def test_a_report_is_not_available_while_the_run_is_going(
    client: TestClient, db_path: Path
) -> None:
    conn = settings.open_database(db_path)
    create_run(conn, "R-busy", {}, settings.today())
    conn.close()

    response = client.get("/runs/R-busy/report")

    assert response.status_code == 409 and "no report yet" in response.json()["detail"]


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if lines:
            events.append(lines)
    return events


def test_progress_streams_as_server_sent_events_and_ends(client: TestClient) -> None:
    run_id = start(client)

    response = client.get(f"/runs/{run_id}/events")

    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert [e["event"] for e in events][:2] == ["resolve", "resolve"]
    assert events[-1]["event"] == "end"
    assert json.loads(events[0]["data"])["step"] == "resolve"
    assert [int(e["id"]) for e in events if "id" in e] == list(range(1, 12))


def test_a_reconnecting_client_receives_only_what_it_missed(client: TestClient) -> None:
    run_id = start(client)

    response = client.get(f"/runs/{run_id}/events", headers={"Last-Event-ID": "9"})

    ids = [int(e["id"]) for e in parse_sse(response.text) if "id" in e]
    assert ids == [10, 11]


def test_events_of_an_unknown_run_are_404(client: TestClient) -> None:
    assert client.get("/runs/R-nope/events").status_code == 404


def test_the_ui_dev_server_is_allowed_by_cors(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
