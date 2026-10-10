from pathlib import Path

import pytest
from pydantic import BaseModel

from bioverdict.resolver.resolver import Resolver, ResolverError
from bioverdict.store.models import LLMResult

from .recorded import make_lookup


class CannedLLM:
    """Answers the resolver's parse step with a fixed form and remembers the prompts."""

    def __init__(self, **form: object) -> None:
        self._form = form
        self.prompts: list[str] = []

    def call(self, step: str, prompt: str, schema: type[BaseModel]) -> LLMResult:
        self.prompts.append(prompt)
        parsed = schema.model_validate(self._form).model_dump(mode="json")
        return LLMResult(step=step, provider="fake", model="fake", parsed=parsed)


def make_resolver(tmp_path: Path, **form: object) -> Resolver:
    return Resolver(make_lookup(tmp_path), CannedLLM(**form))


async def test_a_known_drug_gets_every_id_from_the_databases(tmp_path: Path) -> None:
    resolver = make_resolver(
        tmp_path,
        drug_names=["divarasib"],
        indication="NSCLC",
        targets=["KRAS"],
        action="inhibitor",
        modality="small molecule",
        inferred=["targets", "action"],
    )

    out = await resolver.resolve("divarasib in NSCLC")

    assert [(a.name, a.chembl_id) for a in out.assets] == [("DIVARASIB", "CHEMBL5095236")]
    assert (out.targets[0].symbol, out.targets[0].ensembl, out.targets[0].uniprot) == (
        "KRAS",
        "ENSG00000133703",
        "P01116",
    )
    assert (out.indication.name, out.indication.mondo_id) == (
        "non-small cell lung carcinoma",
        "MONDO_0005233",
    )
    assert (out.action, out.modality) == ("inhibitor", "small molecule")


async def test_registries_are_searched_by_the_typed_name_the_database_name_and_codes(
    tmp_path: Path,
) -> None:
    resolver = make_resolver(tmp_path, drug_names=["divarasib"], targets=["KRAS"])

    out = await resolver.resolve("divarasib")

    assert out.known_assets[0] == "divarasib"  # what the user typed comes first, listed once
    assert "GDC-6036" in out.known_assets  # a development code the registry may use
    assert len(out.known_assets) == len({a.casefold() for a in out.known_assets})
    assert len(out.known_assets) <= 5


async def test_what_the_model_filled_in_is_listed_as_an_assumption(tmp_path: Path) -> None:
    resolver = make_resolver(
        tmp_path,
        drug_names=["divarasib"],
        targets=["KRAS"],
        action="inhibitor",
        inferred=["targets", "action"],
    )

    out = await resolver.resolve("divarasib")

    assert any(a.startswith("targets:") for a in out.assumptions)
    assert any(a.startswith("action:") for a in out.assumptions)


async def test_another_spelling_of_the_same_name_needs_no_disclosure(tmp_path: Path) -> None:
    out = await make_resolver(tmp_path, drug_names=["HRO761"], targets=["WRN"]).resolve("HRO761")

    assert [(a.name, a.chembl_id) for a in out.assets] == [("HRO-761", "CHEMBL6068555")]
    assert not any("HRO" in a for a in out.assumptions)  # HRO761 and HRO-761 are one name


async def test_a_code_for_another_name_is_resolved_and_the_alias_is_disclosed(
    tmp_path: Path,
) -> None:
    resolver = make_resolver(tmp_path, drug_names=["SAR444656"], targets=["IRAK4"])

    out = await resolver.resolve("SAR444656")

    assert [(a.name, a.chembl_id) for a in out.assets] == [("KT-474", "CHEMBL5569030")]
    assert any("'SAR444656'" in a and "KT-474" in a for a in out.assumptions)
    assert out.known_assets[:2] == ["SAR444656", "KT-474"]


async def test_the_modality_comes_from_the_database_when_the_text_gives_none(
    tmp_path: Path,
) -> None:
    out = await make_resolver(tmp_path, drug_names=["STAR-0215"], targets=["KLKB1"]).resolve("x")
    assert out.modality == "antibody"


async def test_a_drug_no_database_knows_gets_no_id_and_says_so(tmp_path: Path) -> None:
    out = await make_resolver(tmp_path, drug_names=["RMC-9805"], targets=["KRAS"]).resolve("x")

    assert [(a.name, a.chembl_id) for a in out.assets] == [("RMC-9805", None)]
    assert out.known_assets == ["RMC-9805"]  # still searched by the name the user gave
    assert any("'RMC-9805'" in a and "not confirmed" in a for a in out.assumptions)


async def test_an_unconfirmed_disease_keeps_its_name_and_no_id(tmp_path: Path) -> None:
    resolver = make_resolver(tmp_path, targets=["WRN"], indication="MSI-high solid tumors")

    out = await resolver.resolve("WRN inhibitor in MSI-high solid tumors")

    assert out.indication.name == "MSI-high solid tumors"
    assert out.indication.mondo_id is None and out.indication.efo_id is None
    assert any("MSI-high solid tumors" in a and "not confirmed" in a for a in out.assumptions)


async def test_indication_and_mechanism_without_a_drug_still_resolve(tmp_path: Path) -> None:
    resolver = make_resolver(tmp_path, targets=["KRAS"], indication="NSCLC", action="inhibitor")

    out = await resolver.resolve("KRAS G12C inhibitor in NSCLC")

    assert out.assets == [] and out.known_assets == []
    assert out.targets[0].ensembl == "ENSG00000133703"
    assert out.indication.mondo_id == "MONDO_0005233"


async def test_without_an_indication_a_known_drug_gets_its_most_advanced_one(
    tmp_path: Path,
) -> None:
    out = await make_resolver(tmp_path, drug_names=["divarasib"], targets=["KRAS"]).resolve("x")

    assert (out.indication.name, out.indication.mondo_id) == (
        "non-small cell lung carcinoma",
        "MONDO_0005233",
    )
    note = next(a for a in out.assumptions if a.startswith("indication:"))
    assert "not stated" in note and "PHASE_3" in note and "also listed" in note


async def test_a_typed_indication_wins_over_the_drugs_own(tmp_path: Path) -> None:
    resolver = make_resolver(
        tmp_path, drug_names=["divarasib"], targets=["KRAS"], indication="NSCLC"
    )

    out = await resolver.resolve("x")

    assert out.indication.mondo_id == "MONDO_0005233"
    assert not any(a.startswith("indication:") for a in out.assumptions)


async def test_without_a_confirmed_drug_or_indication_the_run_can_still_go_on(
    tmp_path: Path,
) -> None:
    out = await make_resolver(tmp_path, targets=["KRAS"]).resolve("x")

    assert out.indication.mondo_id is None
    assert any(a.startswith("indication: none stated") for a in out.assumptions)


async def test_an_unknown_target_symbol_is_kept_without_ids(tmp_path: Path) -> None:
    resolver = make_resolver(tmp_path, drug_names=["divarasib"], targets=["KRAS", "NOTAGENE"])

    out = await resolver.resolve("x")

    assert [t.symbol for t in out.targets] == ["KRAS", "NOTAGENE"]
    assert out.targets[1].ensembl is None
    assert any("'NOTAGENE'" in a for a in out.assumptions)


async def test_without_any_target_there_is_nothing_to_run(tmp_path: Path) -> None:
    with pytest.raises(ResolverError):
        await make_resolver(tmp_path, drug_names=["divarasib"]).resolve("divarasib")


async def test_the_text_reaches_the_model_and_the_form_has_no_id_fields(tmp_path: Path) -> None:
    llm = CannedLLM(drug_names=["divarasib"], targets=["KRAS"])
    await Resolver(make_lookup(tmp_path), llm).resolve("  divarasib in NSCLC  ")

    assert "divarasib in NSCLC" in llm.prompts[0]
    assert "never write database" in llm.prompts[0].lower()
