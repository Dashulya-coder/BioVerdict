"""Every fixture bundle must load against the Bundle contract and be usable by FakeConnector."""

from datetime import date
from pathlib import Path

import pytest

from bioverdict.connectors.fake import FakeConnector
from bioverdict.store.models import Bundle, Indication, ResolverOutput, Target

BUNDLES = sorted((Path(__file__).parents[3] / "fixtures" / "bundles").glob("*.json"))
QUERY = ResolverOutput(indication=Indication(name="NSCLC"), targets=[Target(symbol="KRAS")])


def test_fixture_bundles_exist() -> None:
    assert BUNDLES, "expected at least one fixture bundle"


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
def test_bundle_matches_contract(path: Path) -> None:
    bundle = Bundle.model_validate_json(path.read_text(encoding="utf-8"))
    ids = [e.id for e in bundle.evidence]
    assert len(ids) == len(set(ids)), "evidence ids must be unique"
    catalog = set(bundle.catalog)
    for e in bundle.evidence:
        assert e.url in catalog, f"{e.id}: url missing from catalog"
        assert e.locator is None or e.locator.value in catalog, f"{e.id}: locator missing"


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
def test_bundle_does_not_contain_the_future(path: Path) -> None:
    bundle = Bundle.model_validate_json(path.read_text(encoding="utf-8"))
    for e in bundle.evidence:
        assert e.retrieved_at.date() <= bundle.as_of, f"{e.id} retrieved after the bundle's as_of"
        assert e.published_at is None or e.published_at <= bundle.as_of, (
            f"{e.id} is from the future"
        )


@pytest.mark.parametrize("path", BUNDLES, ids=lambda p: p.stem)
async def test_fake_connector_serves_bundle(path: Path) -> None:
    bundle = Bundle.model_validate_json(path.read_text(encoding="utf-8"))
    result = await FakeConnector.from_bundle_file(path).fetch(QUERY, bundle.as_of)
    assert [e.id for e in result] == [e.id for e in bundle.evidence]


async def test_divarasib_bundle_supports_time_travel() -> None:
    path = next(p for p in BUNDLES if p.stem == "divarasib")
    connector = FakeConnector.from_bundle_file(path)
    before = {e.id for e in await connector.fetch(QUERY, date(2026, 6, 30))}
    after = {e.id for e in await connector.fetch(QUERY, date(2026, 7, 2))}
    assert len(before) >= 8
    assert after - before, "the 2026-07-02 Roche release must appear only after that date"
