"""Cache pre-warm and readiness check for a list of assets (A8). Free: no model is called.

For each asset the Resolver's database lookups and every live connector are run once, which
fills the HTTP cache, and the answer is summarised: which ids were confirmed and how much each
source returned. The form a model would normally fill in from free text comes from the list
instead, so a later live run may ask slightly different questions and miss part of the cache.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

from bioverdict.connectors.opentargets import OpenTargetsError
from bioverdict.pipeline.live_sources import SourcesFactory
from bioverdict.resolver.parse import ParsedInput
from bioverdict.resolver.resolver import Resolver, ResolverError
from bioverdict.store.models import LLMResult


class WarmAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str
    indication: str | None = None
    targets: list[str] = []


class WarmResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset: str
    error: str | None = None  # why nothing could be fetched for this asset
    drug_ids: list[str] = []
    targets: list[str] = []  # "SYMBOL (Ensembl id)" or "SYMBOL (no id)"
    indication: str | None = None  # "name (MONDO/EFO id)" or "name (no id)"
    assumptions: list[str] = []
    evidence: dict[str, int] = {}  # records per source, before any extraction
    failed: list[str] = []  # sources that could not be read at all
    problems: list[str] = []


def load_assets(path: Path) -> list[WarmAsset]:
    """One asset per line: `name <TAB> indication <TAB> TARGET1,TARGET2`. `#` starts a comment;
    the indication and the targets may be left out, but nothing is fetched without a target."""
    assets = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = [field.strip() for field in line.split("\t")]
        if len(fields) > 3 or not fields[0]:
            raise ValueError(f"{path}:{number}: expected name, indication and targets, by tabs")
        fields += [""] * (3 - len(fields))
        targets = [symbol.strip() for symbol in fields[2].split(",") if symbol.strip()]
        assets.append(WarmAsset(asset=fields[0], indication=fields[1] or None, targets=targets))
    return assets


class _TypedForm:
    """Stands where the Resolver expects a model: hands back the form taken from the list."""

    def __init__(self, asset: WarmAsset) -> None:
        self._form = ParsedInput(
            drug_names=[asset.asset], indication=asset.indication, targets=asset.targets
        )

    def call(self, step: str, prompt: str, schema: type[BaseModel]) -> LLMResult:
        parsed = schema.model_validate(self._form.model_dump()).model_dump(mode="json")
        return LLMResult(step=step, provider="list", model="list", parsed=parsed)


async def warm(
    conn: sqlite3.Connection, assets: list[WarmAsset], sources: SourcesFactory, as_of: date
) -> list[WarmResult]:
    results = []
    async with sources(conn) as source:
        for asset in assets:
            result = WarmResult(asset=asset.asset)
            results.append(result)
            try:
                query = await Resolver(source.lookup, _TypedForm(asset)).resolve(asset.asset)
            except (ResolverError, OpenTargetsError, httpx.HTTPError, OSError) as exc:
                result.error = str(exc) if isinstance(exc, ResolverError) else type(exc).__name__
                continue
            result.drug_ids = [a.chembl_id for a in query.assets if a.chembl_id]
            result.targets = [f"{t.symbol} ({t.ensembl or 'no id'})" for t in query.targets]
            disease = query.indication.mondo_id or query.indication.efo_id
            result.indication = f"{query.indication.name} ({disease or 'no id'})"
            result.assumptions = query.assumptions
            for name, tool in sorted(source.tools.items()):
                try:
                    result.evidence[name] = len(await tool.fetch(query, as_of))
                except (OpenTargetsError, httpx.HTTPError, OSError, ValueError, KeyError) as exc:
                    result.failed.append(name)
                    result.problems.append(f"{name}: {type(exc).__name__}")
                result.problems += [
                    f"{name}: {problem}" for problem in getattr(tool, "problems", [])
                ]
    return results


def table(results: list[WarmResult]) -> str:
    sources = sorted({name for result in results for name in [*result.evidence, *result.failed]})
    lines = [
        "| Asset | Drug id | Targets | Indication | " + " | ".join(sources) + " | Problems |",
        "|" + "---|" * (5 + len(sources)),
    ]
    for result in results:
        if result.error:
            cells = [result.asset, "", "", "", *[""] * len(sources), result.error]
        else:
            cells = [
                result.asset,
                ", ".join(result.drug_ids) or "not confirmed",
                ", ".join(result.targets),
                result.indication or "",
                *[str(result.evidence.get(name, "failed")) for name in sources],
                "; ".join(result.problems) or "none",
            ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"
