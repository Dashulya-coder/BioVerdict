import json
import os
import shutil
import socket
import subprocess
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from bioverdict import settings
from bioverdict.cli import main
from bioverdict.pipeline.fixture_run import run_fixture
from bioverdict.store.as_of import is_visible_as_of
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.runs_repo import list_runs, load_claims, load_events

ROOT = Path(__file__).parents[2]
FIXTURES = ROOT / "fixtures"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("USE_FIXTURES", "1")
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES))

    def reject_network(*args, **kwargs):
        raise AssertionError("fixture CLI must not access the network")

    monkeypatch.setattr(socket.socket, "connect", reject_network)


def test_run_exports_the_api_report_and_persists_all_steps(tmp_path, capsys):
    db, output = tmp_path / "run.sqlite", tmp_path / "report.json"
    assert (
        main(
            [
                "run",
                "--asset",
                " Divarasib ",
                "--as-of",
                "2026-10-07",
                "--db",
                str(db),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    streams = capsys.readouterr()
    report = json.loads(streams.out)
    assert json.loads(output.read_text()) == report
    assert "offline" in streams.err and report["run"]["status"] == "done"
    with closing(settings.open_database(db)) as conn:
        run = list_runs(conn)[0]
        assert run.run_id == report["run"]["run_id"] and run.verdict == "Conditional"
        assert load_claims(conn, run.run_id)[0]
        assert load_events(conn, run.run_id)[-1].status == "done"


@pytest.mark.parametrize("cutoff", ["2026-06-30", "2000-01-01"])
def test_as_of_filters_evidence_catalog_and_canned_claims(tmp_path, capsys, cutoff):
    db = tmp_path / "run.sqlite"
    assert main(["run", "--asset", "divarasib", "--as-of", cutoff, "--db", str(db)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["bundle"]["as_of"] == cutoff
    with closing(settings.open_database(db)) as conn:
        run = list_runs(conn)[0]
        bundle = load_bundle(conn, run.run_id)
        claims, links = load_claims(conn, run.run_id)
        assert run.as_of == bundle.as_of == date.fromisoformat(cutoff)
        assert all(is_visible_as_of(e, bundle.as_of) for e in bundle.evidence)
        assert "E-0005" not in bundle.evidence_by_id()  # future press release
        assert not any("improved progression-free" in c.text for c in claims)
        assert not any("poor-prognosis driver" in c.text for c in claims)  # one lost citation
        assert all(link.evidence_id in bundle.evidence_by_id() for link in links)
        if cutoff == "2000-01-01":
            assert bundle.evidence == [] and bundle.catalog == [] and links == []
            assert all(c.basis.value == "unknown" for c in claims)


@pytest.mark.parametrize(
    "extra", [["--asset", "missing"], ["--asset", "divarasib", "--as-of", "bad"]]
)
def test_invalid_input_creates_no_database(tmp_path, extra):
    db = tmp_path / "absent.sqlite"
    with pytest.raises(SystemExit) as exc:
        main(["run", "--db", str(db), *extra])
    assert exc.value.code == 2 and not db.exists()


def test_a_live_run_without_a_model_key_is_rejected_before_writing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    db = tmp_path / "absent.sqlite"
    with pytest.raises(SystemExit) as exc:
        main(["run", "--asset", "divarasib", "--db", str(db)])
    assert exc.value.code == 2 and not db.exists()
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_free_text_needs_a_live_run(tmp_path):
    db = tmp_path / "absent.sqlite"
    with pytest.raises(SystemExit) as exc:
        main(["run", "--query", "KRAS G12C inhibitor in NSCLC", "--db", str(db)])
    assert exc.value.code == 2 and not db.exists()


def test_a_live_run_passes_the_typed_request_on_and_prints_its_report(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setenv("USE_FIXTURES", "0")
    db, asked = tmp_path / "run.sqlite", []

    def stand_in(conn, run_id, text):
        asked.append(text)
        return run_fixture(conn, run_id, "divarasib", FIXTURES)

    assert main(["run", "--query", " KRAS G12C in NSCLC ", "--db", str(db)], live=stand_in) == 0

    streams = capsys.readouterr()
    assert asked == ["KRAS G12C in NSCLC"] and "live" in streams.err
    assert json.loads(streams.out)["executive"]["verdict"]
    with closing(settings.open_database(db)) as conn:
        assert list_runs(conn)[0].input["query"] == "KRAS G12C in NSCLC"


def test_a_failed_live_run_exits_with_its_reason(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("USE_FIXTURES", "0")

    def stand_in(conn, run_id, text):
        return run_fixture(conn, run_id, "no-such-drug", FIXTURES)

    assert main(["run", "--asset", "x", "--db", str(tmp_path / "run.sqlite")], live=stand_in) == 1
    streams = capsys.readouterr()
    assert not streams.out and "failed" in streams.err


def test_tampered_fixture_is_recorded_as_failed_before_rehashing(tmp_path, capsys):
    fixtures, db = tmp_path / "fixtures", tmp_path / "run.sqlite"
    shutil.copytree(FIXTURES, fixtures)
    path = fixtures / "bundles" / "divarasib.json"
    data = json.loads(path.read_text())
    data["evidence"][0]["excerpt"] += " altered"
    path.write_text(json.dumps(data))
    assert main(["run", "--asset", "divarasib", "--fixtures", str(fixtures), "--db", str(db)]) == 1
    streams = capsys.readouterr()
    assert not streams.out and "content_hash" in streams.err
    with closing(settings.open_database(db)) as conn:
        run = list_runs(conn)[0]
        assert run.status == "failed" and load_events(conn, run.run_id)[-1].status == "failed"


def test_output_failure_preserves_the_completed_run(tmp_path, capsys):
    db = tmp_path / "run.sqlite"
    assert main(["run", "--asset", "divarasib", "--db", str(db), "--output", str(tmp_path)]) == 1
    assert not capsys.readouterr().out
    with closing(settings.open_database(db)) as conn:
        assert list_runs(conn)[0].status == "done"


def test_failed_quote_drops_the_whole_claim_even_with_another_valid_link(tmp_path, capsys):
    fixtures, db = tmp_path / "fixtures", tmp_path / "run.sqlite"
    shutil.copytree(FIXTURES, fixtures)
    path = fixtures / "reasoning" / "divarasib.json"
    data = json.loads(path.read_text())
    draft = data["reasoning.mechanism"]["claims"][0]
    draft["links"][0]["quote"] = "a fabricated quotation absent from the fixture"
    path.write_text(json.dumps(data))
    assert (
        main(
            [
                "run",
                "--asset",
                "divarasib",
                "--as-of",
                "2026-10-07",
                "--fixtures",
                str(fixtures),
                "--db",
                str(db),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert not any(c["text"] == draft["text"] for s in report["sections"] for c in s["claims"])
    with closing(settings.open_database(db)) as conn:
        run = list_runs(conn)[0]
        assert not any(link.claim_id == "C-0001" for link in load_claims(conn, run.run_id)[1])
        assert any("rejected claims: C-0001" in e.detail for e in load_events(conn, run.run_id))


@pytest.mark.parametrize(
    "command",
    [[sys.executable, "-m", "bioverdict"], [str(Path(sys.executable).with_name("bioverdict"))]],
)
def test_real_entrypoints_use_env_paths_from_another_directory(tmp_path, command):
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "backend" / "src"),
        "DB_PATH": str(tmp_path / "env.sqlite"),
    }
    result = subprocess.run(
        [*command, "run", "--asset", "divarasib", "--as-of", "2026-10-07"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run"]["status"] == "done"
    assert (tmp_path / "env.sqlite").exists()


def test_eval_writes_its_report_and_succeeds_when_verdicts_are_as_expected(tmp_path, capsys):
    cases, out = tmp_path / "cases.yaml", tmp_path / "results"
    cases.write_text(
        "- {id: d, input: {asset: Divarasib}, as_of: 2026-10-07, expected_verdict: [Conditional]}"
    )

    code = main(["eval", "--cases", str(cases), "--out", str(out), "--db", str(tmp_path / "e.db")])

    streams = capsys.readouterr()
    assert code == 0 and "| d | Conditional | Conditional | yes |" in streams.out
    assert "offline" in streams.err
    assert (out / "results.json").exists() and (out / "summary.md").read_text() == streams.out


def test_eval_fails_on_an_unexpected_verdict_or_a_case_that_cannot_run(tmp_path, capsys):
    cases = tmp_path / "cases.yaml"
    cases.write_text(
        "- {id: wrong, input: {asset: divarasib}, expected_verdict: [Invest]}\n"
        "- {id: absent, input: {asset: HRO761}}\n"
    )

    code = main(
        [
            "eval",
            "--cases",
            str(cases),
            "--out",
            str(tmp_path / "o"),
            "--db",
            str(tmp_path / "e.db"),
        ]
    )

    assert code == 1
    assert "unexpected verdict: wrong; failed runs: absent" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [["--repeat", "0"], ["--cases", "missing.yaml"]])
def test_eval_refuses_bad_arguments_before_writing(tmp_path, extra):
    cases, db = tmp_path / "cases.yaml", tmp_path / "absent.sqlite"
    cases.write_text("- {id: d, input: {asset: divarasib}}")
    arguments = ["eval", "--cases", str(cases), "--out", str(tmp_path / "o"), "--db", str(db)]
    with pytest.raises(SystemExit) as exc:
        main([*arguments, *extra])
    assert exc.value.code == 2 and not db.exists()


def test_warm_reads_the_sources_for_a_list_without_a_model(tmp_path, capsys, monkeypatch):
    from contextlib import asynccontextmanager

    from resolver.recorded import make_lookup

    from bioverdict.connectors.fake import FakeConnector
    from bioverdict.pipeline.live_sources import Sources

    monkeypatch.undo()  # the recorded lookup replays through a mock transport, not a socket

    @asynccontextmanager
    async def sources(conn):
        yield Sources(lookup=make_lookup(tmp_path), tools={"bundle": FakeConnector([], "bundle")})

    listing, output = tmp_path / "assets.tsv", tmp_path / "warm.json"
    listing.write_text("divarasib\tNSCLC\tKRAS\nHRO761\n")

    code = main(
        ["warm", "--list", str(listing), "--db", str(tmp_path / "w.db"), "--output", str(output)],
        sources=sources,
    )

    streams = capsys.readouterr()
    assert code == 1  # the second asset names no target
    assert "| divarasib | CHEMBL5095236 | KRAS (ENSG00000133703) |" in streams.out
    assert "no target" in streams.out and "no model calls" in streams.err
    assert [r["asset"] for r in json.loads(output.read_text())] == ["divarasib", "HRO761"]
