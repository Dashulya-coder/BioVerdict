"""Cache pre-warm: recorded Open Targets answers for the lookups, stand-in connectors."""

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import httpx
import pytest
from resolver.recorded import make_lookup

from bioverdict.connectors.fake import FakeConnector
from bioverdict.eval.warm import WarmAsset, load_assets, table, warm
from bioverdict.pipeline.live_sources import Sources
from bioverdict.store.db import connect
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Bundle, ResolverOutput

FIXTURES = Path(__file__).parents[3] / "fixtures"
EVIDENCE = Bundle.model_validate_json(
    (FIXTURES / "bundles" / "divarasib.json").read_text(encoding="utf-8")
).evidence
TODAY = date(2026, 10, 7)
DIVARASIB = WarmAsset(asset="divarasib", indication="NSCLC", targets=["KRAS"])


class Down:
    name = "registry"

    async def fetch(self, query: ResolverOutput, as_of: date) -> list:
        raise httpx.ConnectError("down")


class Asked:
    """Remembers the resolved question it was asked."""

    name = "papers"

    def __init__(self) -> None:
        self.queries: list[ResolverOutput] = []

    async def fetch(self, query: ResolverOutput, as_of: date) -> list:
        self.queries.append(query)
        return []


def sources(tmp_path: Path, *tools):
    @asynccontextmanager
    async def opened(conn: sqlite3.Connection) -> AsyncIterator[Sources]:
        yield Sources(lookup=make_lookup(tmp_path), tools={tool.name: tool for tool in tools})

    return opened


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    connection = connect(tmp_path / "warm.db")
    migrate(connection)
    yield connection
    connection.close()


async def test_an_asset_is_resolved_by_the_databases_and_every_source_is_read(
    conn, tmp_path
) -> None:
    asked = Asked()
    tools = (FakeConnector(EVIDENCE, name="bundle"), asked)

    (result,) = await warm(conn, [DIVARASIB], sources(tmp_path, *tools), TODAY)

    assert result.error is None and result.problems == []
    assert result.drug_ids == ["CHEMBL5095236"]
    assert result.targets == ["KRAS (ENSG00000133703)"]
    assert result.indication == "non-small cell lung carcinoma (MONDO_0005233)"
    assert result.evidence == {"bundle": 15, "papers": 0}
    (query,) = asked.queries
    assert query.assets[0].chembl_id == "CHEMBL5095236" and "divarasib" in query.known_assets


async def test_a_source_that_is_down_is_named_and_the_others_are_still_read(conn, tmp_path) -> None:
    tools = (FakeConnector(EVIDENCE, name="bundle"), Down())

    (result,) = await warm(conn, [DIVARASIB], sources(tmp_path, *tools), TODAY)

    assert result.evidence == {"bundle": 15} and result.problems == ["registry: ConnectError"]
    assert "failed" in table([result]) and "registry: ConnectError" in table([result])


async def test_an_asset_without_a_target_is_reported_and_the_next_one_still_runs(
    conn, tmp_path
) -> None:
    assets = [WarmAsset(asset="divarasib"), DIVARASIB]
    tool = FakeConnector(EVIDENCE, name="bundle")

    first, second = await warm(conn, assets, sources(tmp_path, tool), TODAY)

    assert first.error is not None and "no target" in first.error and first.evidence == {}
    assert second.error is None and second.evidence == {"bundle": 15}


async def test_a_name_the_database_does_not_confirm_is_said_so(conn, tmp_path) -> None:
    asset = WarmAsset(asset="MariTide", indication="obesity", targets=["GLP1R"])

    (result,) = await warm(conn, [asset], sources(tmp_path, Asked()), TODAY)

    assert result.drug_ids == [] and any("MariTide" in a for a in result.assumptions)
    assert "not confirmed" in table([result])


def test_the_list_is_one_asset_per_line_with_comments(tmp_path: Path) -> None:
    path = tmp_path / "assets.tsv"
    path.write_text(
        "# name, indication, targets\n\ndivarasib\tNSCLC\tKRAS\n"
        "retatrutide\tobesity\tGLP1R, GIPR,GCGR\nHRO761\n",
        encoding="utf-8",
    )

    first, second, third = load_assets(path)

    assert first == DIVARASIB and second.targets == ["GLP1R", "GIPR", "GCGR"]
    assert (third.asset, third.indication, third.targets) == ("HRO761", None, [])


def test_the_example_list_in_the_repository_loads() -> None:
    assert load_assets(FIXTURES.parent / "eval" / "assets_example.tsv") == [DIVARASIB]


def test_a_line_with_too_many_fields_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "assets.tsv"
    path.write_text("a\tb\tC\td\n", encoding="utf-8")
    with pytest.raises(ValueError, match="assets.tsv:1"):
        load_assets(path)
