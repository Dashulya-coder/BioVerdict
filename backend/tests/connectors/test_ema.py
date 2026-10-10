"""The EMA connector on real records of the Agency's open data (fixtures/raw, 2026-10-10)."""

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.ema import (
    COMPETITOR_FAMILY,
    OWN_FAMILY,
    EmaConnector,
    require_medicines,
    select,
)
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.validate import BodyError
from bioverdict.contracts import Connector
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Indication, ResolverOutput, Target

SAMPLE = Path(__file__).parents[3] / "fixtures" / "raw" / "ema_medicines_sample.json"
ROWS = json.loads(SAMPLE.read_text(encoding="utf-8"))["data"]
MS = Indication(name="multiple sclerosis", efo_id="EFO_0803536")
BTK = [Target(symbol="BTK", ensembl="ENSG00000010671")]
TODAY = datetime.now(UTC).date()


def names(chosen: list[tuple[dict, str]]) -> dict[str, str]:
    return {record["name_of_medicine"]: family for record, family in chosen}


def connector(tmp_path: Path, body: bytes | None = None) -> EmaConnector:
    conn = connect(tmp_path / "ema.db")
    migrate(conn)
    content = body if body is not None else SAMPLE.read_bytes()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content))
    )
    return EmaConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()))


def test_the_connector_satisfies_the_contract(tmp_path: Path) -> None:
    assert isinstance(connector(tmp_path), Connector)


def test_a_medicine_authorised_for_the_indication_is_a_competitor() -> None:
    chosen = names(select(ROWS, ResolverOutput(indication=MS, targets=BTK)))

    assert chosen["Cenrifki"] == COMPETITOR_FAMILY and chosen["Ocrevus"] == COMPETITOR_FAMILY
    assert "Imbruvica" not in chosen  # authorised, but not for this disease
    assert "Dimethyl fumarate Accord" not in chosen  # a generic copy
    assert "Extavia" not in chosen  # withdrawn
    assert "Jayempi" not in chosen  # names the disease as one item of a long list


def test_the_asset_itself_is_its_own_record_whatever_its_indication() -> None:
    chosen = names(
        select(ROWS, ResolverOutput(indication=MS, targets=BTK, known_assets=["Tolebrutinib"]))
    )

    assert chosen["Cenrifki"] == OWN_FAMILY


async def test_a_record_is_a_status_fact_dated_by_its_last_update(tmp_path: Path) -> None:
    out = await connector(tmp_path).fetch(ResolverOutput(indication=MS, targets=BTK), TODAY)
    cenrifki = next(e for e in out if "Cenrifki" in e.source)

    assert cenrifki.status_key == "ema:EMEA/H/C/006386"
    assert cenrifki.source == "EMA medicine record: Cenrifki (tolebrutinib)"
    assert "secondary progressive multiple sclerosis" in cenrifki.excerpt
    assert json.loads(cenrifki.excerpt)["medicine_status"] == "Authorised"
    assert cenrifki.published_at is not None and cenrifki.published_at <= TODAY


async def test_a_run_dated_before_the_last_update_does_not_see_the_record(tmp_path: Path) -> None:
    out = await connector(tmp_path).fetch(
        ResolverOutput(indication=MS, targets=BTK), date(2024, 6, 30)
    )

    assert out == []


def test_an_answer_that_is_not_the_register_is_refused() -> None:
    require_medicines(SAMPLE.read_bytes())
    for body in (b"<html>maintenance</html>", b'{"data": "none"}', b"[]"):
        with pytest.raises(BodyError):
            require_medicines(body)


async def test_a_question_without_an_indication_reads_no_competitors(tmp_path: Path) -> None:
    out = await connector(tmp_path).fetch(
        ResolverOutput(indication=Indication(name="not specified"), targets=BTK), TODAY
    )

    assert out == []
