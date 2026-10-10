"""What differs between two finished runs: verdict, gates, chain, evidence and claims (A7).

Pure comparison of stored records; no model is asked. It serves a run recomputed on added
evidence against its original, and two runs of one asset at different cutoffs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from bioverdict.api import report
from bioverdict.api.schemas import (
    ChainLinkChange,
    ChainLinkView,
    ClaimChange,
    ClaimSnapshot,
    DiffResponse,
    GateChange,
    ModuleCause,
    ModuleChange,
    RunSide,
)
from bioverdict.scoring.module_answers import (
    SPECS,
    ModuleId,
    contribution,
    module_answers,
)
from bioverdict.store.evidence_ids import dedup_key
from bioverdict.store.load_bundle import load_bundle
from bioverdict.store.models import Bundle, Claim, ClaimEvidenceLink, Section, VerdictResult
from bioverdict.store.runs_repo import load_claims

MATCHING = (
    "Evidence is paired by source address, locator and exact excerpt. Claims are paired by "
    "section and identical wording: a reworded claim is listed as one removed and one added."
)
EvidenceKey = tuple[str, str, str]
MIN_CONFIDENCE_CHANGE = 0.005


@dataclass(frozen=True)
class _Run:
    run_id: str
    result: VerdictResult
    bundle: Bundle
    claims: list[Claim]
    links: list[ClaimEvidenceLink]

    def keys(self) -> dict[str, EvidenceKey]:
        return {item.id: dedup_key(item) for item in self.bundle.evidence}

    def quoted(self, claim: Claim) -> dict[EvidenceKey, tuple[str, str]]:
        """The evidence a claim quotes, with the direction and the words of each link."""
        keys = self.keys()
        return {
            keys[link.evidence_id]: (link.direction.value, link.quote)
            for link in self.links
            if link.claim_id == claim.id and link.evidence_id in keys
        }


def _load(conn: sqlite3.Connection, run_id: str) -> _Run:
    record = report.require_finished(conn, run_id)
    assert record.result is not None
    claims, links = load_claims(conn, run_id)
    return _Run(run_id, record.result, load_bundle(conn, run_id), claims, links)


def _side(run: _Run) -> RunSide:
    return RunSide(
        run_id=run.run_id,
        as_of=run.bundle.as_of,
        bundle_version=run.bundle.version,
        content_hash=run.bundle.content_hash,
        evidence_count=len(run.bundle.evidence),
        verdict=run.result.verdict,
        confidence=run.result.confidence,
        translation_chain_probability=run.result.translation_chain_probability,
    )


def _snapshot(claim: Claim) -> ClaimSnapshot:
    return ClaimSnapshot(
        id=claim.id,
        basis=claim.basis,
        confidence=claim.confidence,
        gate_signals=claim.gate_signals,
        critical=claim.critical,
    )


def _footing(run: _Run, claim: Claim) -> tuple:
    """What a claim rests on; two claims with the same wording and footing are unchanged."""
    return (
        claim.basis,
        round(claim.confidence, 6),
        tuple(claim.gate_signals),
        claim.critical,
        tuple(sorted(run.quoted(claim).items())),
    )


def _claim_changes(
    base: _Run, head: _Run, added: set[EvidenceKey]
) -> tuple[list[ClaimChange], int]:
    def by_wording(run: _Run) -> dict[tuple[Section, str], Claim]:
        return {(c.section, " ".join(c.text.split())): c for c in run.claims}

    before, after = by_wording(base), by_wording(head)
    head_ids = {key: evidence_id for evidence_id, key in head.keys().items()}
    changes: list[ClaimChange] = []
    unchanged = 0
    for wording in sorted(before.keys() | after.keys(), key=lambda w: (w[0].value, w[1])):
        old, new = before.get(wording), after.get(wording)
        if old and new and _footing(base, old) == _footing(head, new):
            unchanged += 1
            continue
        fresh = sorted(head_ids[key] for key in head.quoted(new) if key in added) if new else []
        claim = new or old
        assert claim is not None
        changes.append(
            ClaimChange(
                change="changed" if old and new else "added" if new else "removed",
                section=claim.section,
                text=claim.text,
                before=_snapshot(old) if old else None,
                after=_snapshot(new) if new else None,
                new_evidence_ids=fresh,
            )
        )
    return changes, unchanged


@dataclass(frozen=True)
class _Moved:
    """A claim of the later run that quotes evidence the earlier run did not have."""

    old: Claim | None
    new: Claim


def _moved_claims(base: _Run, head: _Run, added: set[EvidenceKey]) -> list[_Moved]:
    def wording(claim: Claim) -> tuple[Section, str]:
        return (claim.section, " ".join(claim.text.split()))

    before = {wording(c): c for c in base.claims}
    return [
        _Moved(before.get(wording(claim)), claim)
        for claim in head.claims
        if any(key in added for key in head.quoted(claim))
    ]


def _causes(head: _Run, moved: list[_Moved], added: set[EvidenceKey]) -> list[ModuleCause]:
    keys = head.keys()
    by_id = head.bundle.evidence_by_id()
    causes = []
    for item in moved:
        for link in head.links:
            if link.claim_id != item.new.id or keys.get(link.evidence_id) not in added:
                continue
            evidence = by_id[link.evidence_id]
            causes.append(
                ModuleCause(
                    evidence_id=evidence.id,
                    source=evidence.source,
                    url=evidence.url,
                    published_at=evidence.published_at,
                    level=evidence.level,
                    direction=link.direction,
                    quote=link.quote,
                    claim_id=item.new.id,
                    claim_text=item.new.text,
                    claim_change="changed" if item.old else "added",
                    confidence_before=item.old.confidence if item.old else None,
                    confidence_after=item.new.confidence,
                    contribution_before=contribution(item.old) if item.old else None,
                    contribution_after=contribution(item.new),
                )
            )
    # The evidence that moved a claim furthest first.
    return sorted(
        causes,
        key=lambda c: (-abs(c.contribution_after - (c.contribution_before or 0.0)), c.claim_id),
    )


MIN_BALANCE_CHANGE = 0.005
INVESTMENT_CAUSES = 5


def module_changes(base: _Run, head: _Run, added: set[EvidenceKey]) -> list[ModuleChange]:
    """Each module in both runs, with the new evidence that reached its claims.

    The investment module has no claims of its own: its causes are the new evidence on the
    claims the verdict is decided on (key claims and claims that assert a gate), or, when none
    of those moved, the evidence that moved any claim furthest.
    """
    before = {m.module: m for m in module_answers(base.claims, base.links, base.result)}
    after = module_answers(head.claims, head.links, head.result)
    moved = _moved_claims(base, head, added)
    sections = {spec.module: spec.sections for spec in SPECS}
    everything = _causes(head, moved, added)
    changes = []
    for new in after:
        old = before[new.module]
        if new.module is ModuleId.INVESTMENT:
            deciding = [m for m in moved if m.new.critical or m.new.gate_signals]
            causes = _causes(head, deciding, added) or everything[:INVESTMENT_CAUSES]
        else:
            mine = [m for m in moved if m.new.section in sections[new.module]]
            causes = _causes(head, mine, added)
        if old.balance is None or new.balance is None:
            shifted = old.balance != new.balance
        else:
            shifted = abs(new.balance - old.balance) >= MIN_BALANCE_CHANGE
        changes.append(
            ModuleChange(
                module=new.module,
                title=new.title,
                answer_before=old.answer,
                answer_after=new.answer,
                balance_before=old.balance,
                balance_after=new.balance,
                headline_before=old.headline,
                headline_after=new.headline,
                changed=old.answer is not new.answer or shifted,
                causes=causes,
            )
        )
    return changes


def chain_changes(before: list[ChainLinkView], after: list[ChainLinkView]) -> list[ChainLinkChange]:
    """The links whose status or confidence differs.

    Evidence often strengthens a link without moving it to another status (0.71 to 0.89, both
    `supported`); that is the change a reader is looking for, so it is listed too. A difference
    below `MIN_CONFIDENCE_CHANGE` would not show in the two decimals a report prints.
    """
    changes = []
    for old, new in zip(before, after, strict=True):
        if old.confidence is None or new.confidence is None:
            moved = old.confidence != new.confidence
        else:
            moved = abs(new.confidence - old.confidence) >= MIN_CONFIDENCE_CHANGE
        if old.status != new.status or moved:
            changes.append(
                ChainLinkChange(
                    link=new.link,
                    status_before=old.status,
                    status_after=new.status,
                    confidence_before=old.confidence,
                    confidence_after=new.confidence,
                )
            )
    return changes


def build_diff(conn: sqlite3.Connection, base_id: str, head_id: str) -> DiffResponse:
    """Compare run `head_id` with run `base_id`. Both must be finished."""
    base, head = _load(conn, base_id), _load(conn, head_id)
    base_keys, head_keys = set(base.keys().values()), set(head.keys().values())
    added, removed = head_keys - base_keys, base_keys - head_keys

    fired_before = {gate.gate_id: gate for gate in base.result.gates}
    gates = [
        GateChange(
            gate_id=gate.gate_id,
            kind=gate.kind,
            fired_before=previous.fired if previous else False,
            fired_after=gate.fired,
        )
        for gate in head.result.gates
        if (previous := fired_before.get(gate.gate_id)) is None or previous.fired != gate.fired
    ]
    chain = chain_changes(
        report.translation_chain(base.claims), report.translation_chain(head.claims)
    )
    claims, unchanged = _claim_changes(base, head, added)
    return DiffResponse(
        base=_side(base),
        head=_side(head),
        verdict_changed=base.result.verdict is not head.result.verdict,
        modules=module_changes(base, head, added),
        gates=gates,
        chain=chain,
        evidence_added=[
            report.evidence_view(item, head.links)
            for item in head.bundle.evidence
            if dedup_key(item) in added
        ],
        evidence_removed=[
            report.evidence_view(item, base.links)
            for item in base.bundle.evidence
            if dedup_key(item) in removed
        ],
        claims=claims,
        unchanged_claims=unchanged,
        matching=MATCHING,
    )
