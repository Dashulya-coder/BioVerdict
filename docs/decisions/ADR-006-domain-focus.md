# ADR-006: Single-domain depth with a universal core

**Status:** Proposed
**Date:** 2026-10-06
**Deciders:** TODO

## Context

The task requires a general system that works for any indication x mechanism, and the organizers will test hidden queries. With two people we cannot go deep in several domains. We also need a leakage-resistant test: the organizers' list contains drugs from well-known to very obscure.

## Decision

Keep the core domain-agnostic. Put domain knowledge in a **domain pack** (checklists, endpoints, analog classes, playbooks as configuration). Go deep in one domain: precision oncology (RAS/KRAS and WRN). Verify universality with a light smoke test on a second domain (for example obesity or a cardiovascular siRNA) with no tuning. Run the whole organizer list through the cheap retrieval path to check that nothing breaks.

## Options Considered

| Dimension | A: depth in one domain (chosen) | B: shallow in several | C: all-domain depth |
|---|---|---|---|
| Demo quality | high | medium | not feasible |
| Evidence of generality | via smoke test | direct but shallow | direct |
| Leakage test | good (depth gradient inside the domain) | mixed | mixed |
| Work for two people | feasible | feasible | no |

## Trade-off Analysis

Focus gives real events with dates for the demo and a coherent eval set, while a thin second-domain test protects against overfitting.

## Consequences

- Easier: demo, eval set, reviewer confidence in details.
- Harder: risk that hidden queries hit other domains; mitigated by the generic core and `playbooks/`.
- Revisit after the first smoke test on another domain.

## Action Items

1. [ ] Write the oncology domain pack (`domain-pack-oncology.md`).
2. [ ] Choose the second domain for the smoke test.
3. [ ] Add a generic fallback playbook used when no pack matches.
