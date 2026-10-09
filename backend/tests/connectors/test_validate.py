"""Bodies that must never reach the cache, and empty answers that must."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from tenacity import wait_none

from bioverdict.connectors.epidemiology import PopulationConnector
from bioverdict.connectors.http import CachedHttpClient
from bioverdict.connectors.validate import (
    BodyError,
    contains,
    json_object,
    json_rows,
    world_bank_page,
)
from bioverdict.store.db import connect
from bioverdict.store.http_cache import HttpCache
from bioverdict.store.migrations import migrate
from bioverdict.store.models import Indication, ResolverOutput, Target

# What the World Bank really answers to a bad request, with HTTP 200.
WORLD_BANK_ERROR = b'[{"message":[{"id":"120","key":"Invalid value","value":"not valid"}]}]'
WORLD_BANK_PAGE = (
    b'[{"page":1,"pages":1},[{"indicator":{"id":"SP.POP.TOTL","value":"Population"},'
    b'"country":{"id":"US","value":"United States"},"date":"2025","value":340000000}]]'
)


@pytest.mark.parametrize("body", [b'{"studies": []}', b'{"studies": [{}], "nextPageToken": "x"}'])
def test_an_object_with_its_keys_passes_even_when_empty(body: bytes) -> None:
    json_object("studies")(body)


@pytest.mark.parametrize("body", [b"<html>busy</html>", b"[]", b'{"error": "x"}', b'{"studi'])
def test_an_object_without_its_keys_is_refused(body: bytes) -> None:
    with pytest.raises(BodyError):
        json_object("studies")(body)


def test_any_object_passes_when_no_key_is_required() -> None:
    json_object()(b"{}")  # a study without posted results


def test_rows_may_be_empty_but_must_be_a_list_of_objects() -> None:
    json_rows(b"[]")
    json_rows(b'[{"Brnd_Name": "Lumakras"}]')
    for body in (b'{"message": "error"}', b'["error"]', b"Bad Gateway"):
        with pytest.raises(BodyError):
            json_rows(body)


def test_a_world_bank_error_is_refused_and_a_page_passes() -> None:
    world_bank_page(WORLD_BANK_PAGE)
    world_bank_page(b'[{"page":1,"pages":0},null]')  # no values: a valid answer
    for body in (WORLD_BANK_ERROR, b"[]", b'{"page": 1}'):
        with pytest.raises(BodyError):
            world_bank_page(body)


def test_a_document_cut_short_is_refused() -> None:
    whole = contains(b"<JDBOR", b"</JDBOR>")

    whole(b"<JDBOR><DisorderList/></JDBOR>")
    with pytest.raises(BodyError):
        whole(b"<JDBOR><DisorderList>")


def test_a_refusal_is_a_value_error_so_collection_records_it_as_a_failed_tool() -> None:
    assert issubclass(BodyError, ValueError)


async def test_an_error_inside_a_200_answer_is_not_replayed_by_the_cache(tmp_path: Path) -> None:
    answers = [WORLD_BANK_ERROR]

    def server(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=answers.pop(0) if answers else WORLD_BANK_PAGE)

    conn = connect(tmp_path / "v.db")
    migrate(conn)
    client = httpx.AsyncClient(transport=httpx.MockTransport(server))
    population = PopulationConnector(CachedHttpClient(client, HttpCache(conn), wait=wait_none()))
    asked = ResolverOutput(
        indication=Indication(name="obesity", mondo_id="MONDO_0011122"),
        targets=[Target(symbol="GLP1R")],
    )
    today = datetime.now(UTC).date()

    with pytest.raises(BodyError):
        await population.fetch(asked, today)

    assert await population.fetch(asked, today)  # asked again, and the real page is read
