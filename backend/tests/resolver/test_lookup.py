from pathlib import Path

import pytest

from bioverdict.resolver.names import MatchKind

from .recorded import make_lookup

DIVARASIB = "CHEMBL5095236"


@pytest.mark.parametrize(
    "name, chembl_id",
    [
        ("divarasib", DIVARASIB),
        ("divarasib adipate", DIVARASIB),  # a salt resolves to its parent drug
        ("SAR444656", "CHEMBL5569030"),  # a code: KT-474
        ("HRO761", "CHEMBL6068555"),  # the database writes it HRO-761
        ("STAR-0215", "CHEMBL6068148"),  # navenibart
        ("sonelokimab", "CHEMBL4298023"),  # listed as a synonym of M-1095
        ("retatrutide", "CHEMBL5095485"),
        # ION582 is a listed synonym of the sodium salt; Open Targets links it to nothing else.
        ("ION582", "CHEMBL6068612"),
    ],
)
async def test_known_drugs_resolve_by_name_code_or_synonym(
    tmp_path: Path, name: str, chembl_id: str
) -> None:
    resolution = await make_lookup(tmp_path).find_drug(name)
    assert resolution.chosen is not None and resolution.chosen.chembl_id == chembl_id


async def test_the_drug_type_comes_from_the_database(tmp_path: Path) -> None:
    lookup = make_lookup(tmp_path)
    assert (await lookup.find_drug("divarasib")).drug_type == "Small molecule"
    assert (await lookup.find_drug("STAR-0215")).drug_type == "Antibody"


@pytest.mark.parametrize("name", ["RMC-9805", "elisrasib", "MariTide"])
async def test_a_drug_the_database_does_not_know_is_not_guessed(tmp_path: Path, name: str) -> None:
    resolution = await make_lookup(tmp_path).find_drug(name)
    assert resolution.chosen is None


@pytest.mark.parametrize(
    "symbol, ensembl, uniprot",
    [
        ("KRAS", "ENSG00000133703", "P01116"),
        ("KRAS2", "ENSG00000133703", "P01116"),  # an old alias of KRAS, and of nothing else
        ("WRN", "ENSG00000165392", "Q14191"),
        ("GLP1R", "ENSG00000112164", "P43220"),
    ],
)
async def test_targets_resolve_to_ensembl_and_uniprot(
    tmp_path: Path, symbol: str, ensembl: str, uniprot: str
) -> None:
    match = await make_lookup(tmp_path).find_target(symbol)
    assert match is not None
    assert (match.ensembl, match.uniprot) == (ensembl, uniprot)


async def test_an_unknown_target_is_not_guessed(tmp_path: Path) -> None:
    assert await make_lookup(tmp_path).find_target("NOTAGENE") is None


@pytest.mark.parametrize(
    "name, mondo_id",
    [
        ("NSCLC", "MONDO_0005233"),  # an abbreviation listed as a synonym
        ("obesity", "MONDO_0011122"),
        ("Alzheimer's disease", "MONDO_0004975"),
        ("hypertension", "MONDO_0005044"),
        ("hidradenitis suppurativa", "MONDO_0006559"),
    ],
)
async def test_diseases_resolve_to_mondo_ids(tmp_path: Path, name: str, mondo_id: str) -> None:
    resolution = await make_lookup(tmp_path).find_disease(name)
    assert resolution.chosen is not None and resolution.chosen.id == mondo_id


async def test_an_exact_name_ranks_as_a_name_match(tmp_path: Path) -> None:
    resolution = await make_lookup(tmp_path).find_disease("hidradenitis suppurativa")
    assert resolution.chosen is not None and resolution.chosen.kind is MatchKind.NAME


@pytest.mark.parametrize("name", ["multiple sclerosis", "MSI-high solid tumors"])
async def test_a_trait_that_merely_lists_the_name_is_not_taken_for_the_disease(
    tmp_path: Path, name: str
) -> None:
    """'multiple sclerosis symptom measurement' lists 'multiple sclerosis' as a synonym."""
    resolution = await make_lookup(tmp_path).find_disease(name)
    assert resolution.chosen is None and resolution.candidates == ()
