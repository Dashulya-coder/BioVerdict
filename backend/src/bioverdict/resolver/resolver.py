"""The Resolver: what the user typed in, a `ResolverOutput` with confirmed identifiers out (A1).

One cheap LLM call reads the free text (`parse.py`). Everything that has an identifier is then
looked up in Open Targets (`lookup.py`): the model never writes one. Whatever could not be
confirmed, and whatever the model filled in beyond the text, is listed in `assumptions`, so a
reader sees what is established and what is a guess.
"""

from __future__ import annotations

import re

from bioverdict.contracts import LLM
from bioverdict.resolver.lookup import DrugResolution, OpenTargetsLookup
from bioverdict.resolver.names import normalize
from bioverdict.resolver.parse import ParsedInput, parse_input
from bioverdict.store.models import Asset, Indication, ResolverOutput, Target

# How Open Targets classifies a drug, in the words the rest of the system uses.
MODALITY_BY_DRUG_TYPE = {
    "Small molecule": "small molecule",
    "Antibody": "antibody",
    "Oligonucleotide": "oligonucleotide",
    "Protein": "protein",
}
MAX_CODE_SYNONYMS = 3  # registries list drugs under their development codes


class ResolverError(RuntimeError):
    """The input cannot be turned into a run: no target could be identified."""


def _code_like(label: str) -> bool:
    """Development codes such as GDC-6036 or RG6330 contain a digit; plain names do not."""
    return bool(re.search(r"\d", label))


def _search_names(typed: str, resolution: DrugResolution) -> list[str]:
    """What to search registries with: what the user typed, the database name, a few codes."""
    names = [typed]
    if resolution.chosen is not None:
        names.append(resolution.chosen.name)
        names += [s for s in resolution.chosen.synonyms if _code_like(s)][:MAX_CODE_SYNONYMS]
    unique: dict[str, str] = {}  # the same name spelled differently is listed once
    for name in names:
        unique.setdefault(normalize(name), name)
    return list(unique.values())


class Resolver:
    def __init__(self, lookup: OpenTargetsLookup, llm: LLM) -> None:
        self._lookup = lookup
        self._llm = llm

    async def resolve(self, text: str) -> ResolverOutput:
        parsed = await parse_input(self._llm, text)
        assumptions = [
            f"{field}: not stated in the input, filled in by the model" for field in parsed.inferred
        ]

        assets, search_names, drug_type = await self._resolve_assets(parsed, assumptions)
        targets = await self._resolve_targets(parsed, assumptions)
        indication = await self._resolve_indication(parsed, assets, assumptions)

        if not targets:
            raise ResolverError(f"no target could be identified from: {text!r}")

        return ResolverOutput(
            indication=indication,
            targets=targets,
            action=parsed.action,
            modality=parsed.modality or MODALITY_BY_DRUG_TYPE.get(drug_type or ""),
            delivery=parsed.delivery,
            tissue=parsed.tissue,
            known_assets=search_names,
            assets=assets,
            assumptions=assumptions,
        )

    async def _resolve_assets(
        self, parsed: ParsedInput, assumptions: list[str]
    ) -> tuple[list[Asset], list[str], str | None]:
        assets: list[Asset] = []
        search_names: list[str] = []
        drug_type: str | None = None

        for typed in dict.fromkeys(parsed.drug_names):
            resolution = await self._lookup.find_drug(typed)
            chosen = resolution.chosen
            if chosen is None:
                assets.append(Asset(name=typed))
                assumptions.append(_unconfirmed_drug(typed, resolution))
            else:
                assets.append(Asset(name=chosen.name, chembl_id=chosen.chembl_id))
                drug_type = drug_type or resolution.drug_type
                if normalize(typed) != normalize(chosen.name):
                    assumptions.append(
                        f"{typed!r} is listed in Open Targets as a name of {chosen.name} ({chosen.chembl_id})"
                    )
            search_names += _search_names(typed, resolution)

        return assets, list(dict.fromkeys(search_names)), drug_type

    async def _resolve_targets(self, parsed: ParsedInput, assumptions: list[str]) -> list[Target]:
        targets: list[Target] = []
        for symbol in dict.fromkeys(parsed.targets):
            match = await self._lookup.find_target(symbol)
            if match is None:
                targets.append(Target(symbol=symbol))
                assumptions.append(f"target {symbol!r} was not found in Open Targets: no ids")
            else:
                targets.append(
                    Target(symbol=match.symbol, uniprot=match.uniprot, ensembl=match.ensembl)
                )
        return targets

    async def _resolve_indication(
        self, parsed: ParsedInput, assets: list[Asset], assumptions: list[str]
    ) -> Indication:
        if not parsed.indication:
            return await self._indication_of_drug(assets, assumptions)

        resolution = await self._lookup.find_disease(parsed.indication)
        if resolution.chosen is None:
            candidates = ", ".join(f"{m.name} ({m.id})" for m in resolution.candidates[:3])
            reason = f"ambiguous between {candidates}" if candidates else "no matching disease term"
            assumptions.append(f"indication {parsed.indication!r} was not confirmed: {reason}")
            return Indication(name=parsed.indication)

        chosen = resolution.chosen
        is_mondo = chosen.id.startswith("MONDO_")
        return Indication(
            name=chosen.name,
            mondo_id=chosen.id if is_mondo else None,
            efo_id=None if is_mondo else chosen.id,
        )

    async def _indication_of_drug(self, assets: list[Asset], assumptions: list[str]) -> Indication:
        """No disease was typed: take the one a confirmed drug is furthest along in.

        This is a choice the user did not make, so it is written into the assumptions with the
        other indications of the drug; a typed indication always wins.
        """
        drug = next((a for a in assets if a.chembl_id), None)
        listed = (
            await self._lookup.drug_indications(drug.chembl_id) if drug and drug.chembl_id else []
        )
        listed = [i for i in listed if i.stage != "UNKNOWN"]
        if drug is None or not listed:
            assumptions.append("indication: none stated, so no disease evidence can be fetched")
            return Indication(name="not specified")
        best = listed[0]
        others = ", ".join(f"{i.name} ({i.stage})" for i in listed[1:4])
        assumptions.append(
            f"indication: not stated; {best.name} ({best.stage}) is the most advanced indication "
            f"of {drug.name} in Open Targets" + (f"; also listed: {others}" if others else "")
        )
        is_mondo = best.disease_id.startswith("MONDO_")
        return Indication(
            name=best.name,
            mondo_id=best.disease_id if is_mondo else None,
            efo_id=None if is_mondo else best.disease_id,
        )


def _unconfirmed_drug(typed: str, resolution: DrugResolution) -> str:
    if resolution.matched:
        names = ", ".join(c.name for c in resolution.matched)
        return f"drug {typed!r} is ambiguous in Open Targets ({names}): no id chosen"
    return f"drug {typed!r} was not confirmed in Open Targets: no id, searched by name only"
