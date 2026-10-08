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
