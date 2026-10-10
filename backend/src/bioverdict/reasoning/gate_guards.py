"""Code checks that a kill-criterion claim rests on evidence of the right kind.

The model tags a claim with a gate it thinks the claim asserts; the verdict then follows from the
claim's confidence. A confident claim about the wrong thing (a trial stopped for business reasons
tagged K1) would fire a hard gate. So a gate signal is kept only if the cited evidence shows the
specific kind of fact the gate is about. The guard is a necessary condition, not a sufficient one:
the model still has to make the claim, and scoring still weighs it.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from bioverdict.reasoning.negation import has_unnegated
from bioverdict.reasoning.stop_reason import (
    StopReason,
    classify_stop_reason,
    overall_status,
    why_stopped,
    without_lifted_holds,
)
from bioverdict.store.models import ClaimEvidenceLink, Evidence, EvidenceLevel, GateId

Support = list[tuple[ClaimEvidenceLink, Evidence]]
GateGuard = Callable[[GateId, Support], str | None]

_STOPPED = {"TERMINATED", "WITHDRAWN"}
_SAFETY_ACTION = re.compile(
    r"clinical hold|boxed warning|black box|withdrawn from the market|market withdrawal"
    r"|partial hold|dosing (?:was )?(?:halted|suspended)",
    re.IGNORECASE,
)
_PROGRAM_STOPPED = re.compile(
    r"discontinu|deprioriti[sz]|halt(?:ed|ing)? (?:the )?(?:development|program)"
    r"|terminat(?:ed|ion) (?:of )?(?:the )?(?:development|program)|ceas(?:ed|ing) development"
    r"|no longer (?:pursu|develop)|removed from (?:the )?pipeline",
    re.IGNORECASE,
)
MIN_COMPETITOR_GROUPS = 3


def stop_reason_of(evidence: Evidence) -> StopReason:
    """A registry status record is judged by its own `whyStopped`; any other text by its words."""
    if overall_status(evidence.excerpt) is not None or evidence.excerpt.lstrip().startswith("{"):
        return classify_stop_reason(why_stopped(evidence.excerpt))
    return classify_stop_reason(evidence.excerpt)


def _stopped_in_registry(evidence: Evidence) -> bool:
    return (overall_status(evidence.excerpt) or "").upper() in _STOPPED


def evidence_guard(gate: GateId, support: Support) -> str | None:
    """None if `support` can back `gate`; otherwise why it cannot."""
    evidence = [ev for _, ev in support]
    if gate is GateId.K1:
        if any(stop_reason_of(ev) is StopReason.EFFICACY for ev in evidence):
            return None
        return "no cited evidence states a stop for lack of efficacy (futility, endpoint not met)"
    if gate is GateId.K2:
        if any(
            stop_reason_of(ev) is StopReason.SAFETY
            or has_unnegated(_SAFETY_ACTION, without_lifted_holds(ev.excerpt))
            for ev in evidence
        ):
            return None
        return "no cited evidence states a safety stop, clinical hold or boxed warning"
    if gate is GateId.K3:
        if any(ev.level is EvidenceLevel.HUMAN_GENETICS for ev in evidence):
            return None
        return "no cited evidence is human genetics"
    if gate is GateId.K4:
        if any(
            _stopped_in_registry(ev)
            or (
                not ev.excerpt.lstrip().startswith("{")
                and has_unnegated(_PROGRAM_STOPPED, ev.excerpt)
            )
            for ev in evidence
        ):
            return None
        return "no cited evidence shows a terminated or withdrawn study or a discontinued program"
    if gate is GateId.S4:
        groups = {ev.independence_group for ev in evidence}
        if len(groups) >= MIN_COMPETITOR_GROUPS:
            return None
        return (
            f"{len(groups)} independent source(s) cited; competitors of one sponsor or paper "
            f"count once, at least {MIN_COMPETITOR_GROUPS} are needed"
        )
    return None  # S5, S6 and the rest: no code check yet
