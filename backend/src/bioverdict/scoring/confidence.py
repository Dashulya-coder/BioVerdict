"""Claim confidence as log-odds aggregation of weighted evidence (Unobio plan, formula section)."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from math import prod

from bioverdict.scoring.config import ConfidenceConfig
from bioverdict.store.models import (
    Claim,
    ClaimEvidenceLink,
    ConfidenceParts,
    Direction,
    Evidence,
    ServiceFlag,
    SourceKind,
)

# Biological and literature evidence ages; registry and company records are "latest wins",
# which the connectors handle, so they are not decayed here.
_DECAYING = {SourceKind.PEER_REVIEWED, SourceKind.PREPRINT, SourceKind.REGULATOR}


@dataclass(frozen=True)
class ConfidenceResult:
    confidence: float
    parts: ConfidenceParts
    flags: list[ServiceFlag]
    support_sum: float  # sum of weights of supporting evidence
    contra_sum: float  # sum of weights of contradicting evidence


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def recency(evidence: Evidence, as_of: date, cfg: ConfidenceConfig) -> float:
    if evidence.source_kind not in _DECAYING:
        return 1.0
    if evidence.published_at is None:
        return cfg.unknown_date_recency
    age_years = max((as_of - evidence.published_at).days, 0) / 365.25
    return 0.5 ** (age_years / cfg.half_life_years)


def _weights(
    claim: Claim,
    items: list[tuple[ClaimEvidenceLink, Evidence]],
    as_of: date,
    cfg: ConfidenceConfig,
) -> list[tuple[float, float]]:
    """Return (weight w_i, recency R) per item, with the independence multiplier applied.

    Evidence of one independence group and one direction is sorted by weight; the k-th item
    gets `independence_decay ** (k - 1)`.
    """
    base: list[tuple[str, float, float]] = []  # (group key, w before I_k, R)
    for link, ev in items:
        r = recency(ev, as_of, cfg)
        w = cfg.level_weight[claim.claim_type][ev.level] * cfg.source_quality[ev.source_kind] * r
        base.append((f"{link.direction}:{ev.independence_group}", w, r))
    grouped: dict[str, list[int]] = defaultdict(list)
    for idx, (key, _, _) in enumerate(base):
        grouped[key].append(idx)
    out: list[tuple[float, float]] = [(0.0, 0.0)] * len(base)
    for idxs in grouped.values():
        for k, idx in enumerate(sorted(idxs, key=lambda i: -base[i][1])):
            out[idx] = (base[idx][1] * cfg.independence_decay**k, base[idx][2])
    return out


def claim_confidence(
    claim: Claim,
    links: list[ClaimEvidenceLink],
    evidence: dict[str, Evidence],
    as_of: date,
    cfg: ConfidenceConfig | None = None,
) -> ConfidenceResult:
    """Confidence of one claim from its evidence links.

    Dropped before counting: neutral links, links to unknown evidence, links whose quote does
    not occur in the excerpt (not grounded), and evidence published after `as_of` (time travel).
    """
    cfg = cfg or ConfidenceConfig()
    items = [
        (link, evidence[link.evidence_id])
        for link in links
        if link.claim_id == claim.id
        and link.direction is not Direction.NEUTRAL
        and link.evidence_id in evidence
        and link.quote in evidence[link.evidence_id].excerpt
        and not (
            evidence[link.evidence_id].published_at
            and evidence[link.evidence_id].published_at > as_of
        )
    ]
    if not items:
        return ConfidenceResult(
            confidence=cfg.no_evidence_confidence,
            parts=ConfidenceParts(support=0.0, contra=0.0, freshness=0.0),
            flags=[ServiceFlag.SPARSE],
            support_sum=0.0,
            contra_sum=0.0,
        )

    weights = _weights(claim, items, as_of, cfg)
    support_ws, contra_ws, rec = [], [], []
    for (link, _), (w, r) in zip(items, weights, strict=True):
        (support_ws if link.direction is Direction.SUPPORTS else contra_ws).append(w)
        rec.append(r)

    support_sum, contra_sum = sum(support_ws), sum(contra_ws)
    score = support_sum - cfg.contra_multiplier * contra_sum
    confidence = sigmoid(logit(cfg.p0) + cfg.kappa * score)

    flags: list[ServiceFlag] = []
    if support_sum + contra_sum < cfg.sparse_threshold:
        flags.append(ServiceFlag.SPARSE)
    if min(support_sum, contra_sum) > cfg.contested_threshold:
        flags.append(ServiceFlag.CONTESTED)

    parts = ConfidenceParts(  # display only: the verdict uses `confidence`
        support=1 - prod(1 - min(w, 1.0) for w in support_ws),
        contra=1 - prod(1 - min(w, 1.0) for w in contra_ws),
        freshness=sum(rec) / len(rec),
    )
    return ConfidenceResult(confidence, parts, flags, support_sum, contra_sum)


def chain_probability(
    link_confidences: list[float], cfg: ConfidenceConfig | None = None
) -> tuple[float, list[int]]:
    """Probability of the translation chain = product of link confidences.

    Also returns the indexes of missing links (confidence below the threshold).
    """
    cfg = cfg or ConfidenceConfig()
    missing = [i for i, c in enumerate(link_confidences) if c < cfg.missing_link_threshold]
    return prod(link_confidences), missing
