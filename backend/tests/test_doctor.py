"""`bioverdict doctor` with stand-in sources: no network, no model, no real key."""

import json
import shutil
from pathlib import Path

import httpx
import pytest

from bioverdict.cli import main
from bioverdict.doctor import Check, check_sources, render, run_checks

FIXTURES = Path(__file__).parents[2] / "fixtures"
UP = {"Registry": lambda client: "data as of today"}


def down(client: httpx.Client) -> str:
    request = httpx.Request("GET", "https://example.org/secret-path?token=abc")
    raise httpx.HTTPStatusError("boom", request=request, response=httpx.Response(503))


@pytest.fixture(autouse=True)
def environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("USE_FIXTURES", "1")
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("FIXTURES_DIR", str(FIXTURES))
    for name in ("ANTHROPIC_API_KEY", "HTTP_CACHE_MAX_AGE_H", "RUN_BUDGET_USD", "RUN_TIMEOUT_S"):
        monkeypatch.delenv(name, raising=False)


def checks(tmp_path: Path, **options) -> dict[str, Check]:
    found = run_checks(tmp_path / "doctor.sqlite", sources=UP, **options)
    return {check.name: check for check in found}


def test_a_fresh_fixture_setup_is_ready_with_two_notes(tmp_path: Path) -> None:
    found = checks(tmp_path)

    assert [c.name for c in found.values() if c.status == "fail"] == []
    assert found["mode"].detail.startswith("fixtures")
    assert found["model key"].status == "warn"  # fine for fixtures, said aloud
    assert found["database"].status == "ok" and "created, schema 3/3" in found["database"].detail
    assert found["source cache"].status == "warn" and "never expire" in found["source cache"].detail
    assert "divarasib" in found["fixtures"].detail and found["Registry"].status == "ok"


def test_a_live_setup_without_a_model_key_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("USE_FIXTURES", "0")

    found = checks(tmp_path)

    assert found["mode"].detail.startswith("live") and found["model key"].status == "fail"


def test_a_key_is_reported_as_set_and_never_printed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("USE_FIXTURES", "0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-very-secret")

    found = run_checks(tmp_path / "doctor.sqlite", sources=UP)

    key = next(check for check in found if check.name == "model key")
    assert key.status == "ok" and "not verified" in key.detail
    assert "sk-very-secret" not in render(found)


@pytest.mark.parametrize("name", ["RUN_BUDGET_USD", "RUN_TIMEOUT_S"])
def test_an_unreadable_limit_fails(tmp_path: Path, monkeypatch, name: str) -> None:
    monkeypatch.setenv(name, "a lot")
    assert checks(tmp_path)["run limits"].status == "fail"


def test_the_cache_policy_is_shown_and_a_bad_one_fails(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HTTP_CACHE_MAX_AGE_H", "12")
    assert "expire after 12 h" in checks(tmp_path)["source cache"].detail

    monkeypatch.setenv("HTTP_CACHE_MAX_AGE_H", "soon")
    assert checks(tmp_path)["source cache"].status == "fail"


def test_a_database_that_cannot_be_opened_fails(tmp_path: Path) -> None:
    (tmp_path / "doctor.sqlite").write_bytes(b"this is not a database, it is a text file")
    assert checks(tmp_path)["database"].status == "fail"


def test_a_tampered_fixture_fails(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, fixtures)
    path = fixtures / "bundles" / "divarasib.json"
    data = json.loads(path.read_text())
    data["evidence"][0]["excerpt"] += " altered"
    path.write_text(json.dumps(data))

    found = run_checks(tmp_path / "doctor.sqlite", fixtures, sources=UP)

    fixture = next(check for check in found if check.name == "fixtures")
    assert fixture.status == "fail" and "content_hash" in fixture.detail


def test_a_source_that_is_down_fails_without_copying_its_address_or_body() -> None:
    (check,) = check_sources({"Registry": down})

    assert check.status == "fail" and check.detail == "did not answer as expected (HTTP 503)"


def test_offline_skips_the_sources_and_says_so(tmp_path: Path) -> None:
    found = run_checks(tmp_path / "doctor.sqlite", offline=True, sources={"Registry": down})

    assert [c.status for c in found if c.name == "sources"] == ["warn"]
    assert not any(c.name == "Registry" for c in found)


def test_the_command_prints_every_check_and_exits_by_the_worst(tmp_path: Path, capsys) -> None:
    db = str(tmp_path / "doctor.sqlite")

    assert main(["doctor", "--db", db], probes=UP) == 0
    ready = capsys.readouterr().out
    assert main(["doctor", "--db", db], probes={"Registry": down}) == 1
    broken = capsys.readouterr().out

    assert "ok    Registry" in ready and ready.rstrip().endswith("0 fail")
    assert "fail  Registry" in broken and broken.rstrip().endswith("1 fail")
