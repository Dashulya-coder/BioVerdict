"""The one LLM step of the Resolver: free text in, a form out (A1).

The model reads what the user typed ("divarasib", "KRAS G12C inhibitor in NSCLC", "KT-474 for
hidradenitis suppurativa") and fills in names and plain-language fields. It never produces an
identifier: ChEMBL, Ensembl, UniProt and MONDO ids come from database lookups (`lookup.py`).
Whatever it adds beyond the text is named in `inferred` and ends up in the output's `assumptions`.
"""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict, Field

from bioverdict.contracts import LLM

STEP = "resolver"

PROMPT = """\
You prepare the input of a biotech due-diligence run. Read the text and fill in the form.
Use only what the text says or makes certain. Do not invent anything, and never write database
identifiers (ChEMBL, Ensembl, UniProt, MONDO, NCT).

- drug_names: names or codes of drugs, copied exactly as written. Leave empty if the text names
  no drug.
- indication: the disease or condition, in its usual name.
- targets: HGNC gene symbols of the molecular targets, when the text names them or the mechanism
  makes them certain: "KRAS G12C inhibitor" gives KRAS; "GLP-1/GIP/glucagon triple agonist" gives
  GLP1R, GIPR and GCGR.
- action: one of agonist, antagonist, inhibitor, degrader, knockdown, upregulation.
- modality: for example small molecule, antibody, siRNA, ASO, peptide.
- delivery: for example oral, SC, IV, intrathecal.
- tissue: the tissue or organ the drug has to act in, if it matters.
- inferred: the names of the fields above that the text does not state and that you filled in
  from the mechanism or from general knowledge.

Text:
{text}
"""


class ParsedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drug_names: list[str] = Field(default_factory=list)
    indication: str | None = None
    targets: list[str] = Field(default_factory=list)
    action: str | None = None
    modality: str | None = None
    delivery: str | None = None
    tissue: str | None = None
    inferred: list[str] = Field(default_factory=list)


async def parse_input(llm: LLM, text: str) -> ParsedInput:
    """Ask the model for the form. The call blocks, so it runs off the event loop."""
    result = await asyncio.to_thread(llm.call, STEP, PROMPT.format(text=text.strip()), ParsedInput)
    return ParsedInput.model_validate(result.parsed)
