# Data model

This document is the contract between the data/verdict side and the analysis/UI side. Changes require both approvals (see `CONTRIBUTING.md`).

## Basis labels

Every claim has a `basis`.

| basis | Meaning |
|---|---|
| `extracted` | copied from a source, with a verbatim quote |
| `derived` | calculated by code from extracted numbers using a fixed rule |
| `inferred` | model judgement over the bundle, no calculation behind it |
| `modeled` | follows from assumptions (PoS, rNPV, market size, uptake, capital) |
| `hypothesis` | plausible but not supported by the bundle |
| `unknown` | not in the bundle; must carry a status and a diligence type |

Valuation and probabilities are always `modeled`, with the assumptions visible.

## Section status

`found` | `conflicting` | `not_reported` | `none_found` | `not_searched` | `error` | `incomplete`

- `not_reported`: the record exists but the value was never published (for example a trial with no posted results). Not a negative.
- `none_found`: the right source was queried and is genuinely empty. Name the source.
- `not_searched`: skipped on purpose (for example no FDA label for an unapproved drug).
- `error`: the fetch failed. The cell proves nothing; re-run.

## Evidence

```json
{
  "id": "E-0042",
  "source": "ClinicalTrials.gov",
  "source_family": "registry",
  "source_kind": "registry",
  "type": "source_fact",
  "url": "https://clinicaltrials.gov/study/NCT00000000",
  "locator": { "type": "nct", "value": "NCT00000000" },
  "excerpt": "verbatim text from the document",
  "published_at": "2026-07-02",
  "retrieved_at": "2026-10-06T10:15:00Z",
  "level": "human_interventional",
  "independence_group": "sponsor:<name>",
  "status_key": null,
  "version": 1
}
```

`type` is `source_fact` or `ai_inference`. `source_kind` drives the source-quality multiplier Q: `peer_reviewed`, `regulator`, `registry` (1.0), `preprint` (0.7), `company` (0.5), `ai_inference` (0.3).

`level` values, strongest first: `human_genetics`, `human_interventional`, `human_observational`, `animal_in_vivo`, `in_vitro`. A sixth, `registry_record`, is outside that scale: it marks a record that a study or program exists (status, phase, sponsor, design, stated endpoints) rather than what it found, and carries no weight for efficacy claims. Results posted in a registry are `human_interventional`.

`independence_group` is the lab or sponsor. Repeated reports of one result count once.

`status_key` marks a status fact whose newer record replaces the older one, for example `nct:NCT06497556:overall_status` for a trial's recruitment status. Connectors set it only for such facts and leave it `null` for everything else (a trial's summary, endpoints and results do not replace each other, although they share a `url` and `locator`). When a bundle holds several items with the same non-null `status_key`, only the one with the latest `published_at` (retrieval date if undated) is kept; the older ones stay in the evidence store, so earlier bundle versions are unchanged.

**Stance belongs to the link, not to the evidence.** The same document can support one claim and contradict another, so `direction` is stored on the claim-evidence link (below), not on the evidence itself.

## Claim

```json
{
  "id": "C-0117",
  "run_id": "R-...",
  "section": "translation",
  "claim_type": "drug_acts_in_humans",
  "flags": [],
  "text": "claim in plain language",
  "basis": "extracted",
  "status": "found",
  "confidence": 0.74,
  "confidence_parts": { "support": 0.82, "contra": 0.10, "freshness": 0.95, "independent_groups": 2 },
  "depends_on": ["C-0102"],
  "diligence_type": null,
  "implication": "favourable"
}
```

Link:

```json
{ "claim_id": "C-0117", "evidence_id": "E-0042", "direction": "supports", "quote": "verbatim, must occur in the evidence excerpt" }
```

`claim_type` (`target_causal` | `drug_acts_in_humans` | `study_fact` | `other`) selects the column of the level-weight table in [`scoring.md`](scoring.md). `flags` holds `sparse`, `contested`, `missing_link`. `chain_link` (`molecular_effect` | `human_exposure` | `target_engagement` | `biological_response` | `patient_benefit`) places a claim on the translation chain. `gate_signals` lists the gates (`K1`..`K5`, `S1`..`S6`) whose condition the claim asserts; code decides whether the gate fires. `critical` marks key claims for the verdict. `implication` (`favourable` | `unfavourable` | `neutral`) says what the claim means for an investor if it is true. The model proposes it; code sets `neutral` on every `unknown` and `unfavourable` on a claim that asserts a gate. It feeds the per-module answers ([`scoring.md`](scoring.md), "Module answers") and never the verdict.

`diligence_type` for `unknown` claims: `proprietary_data` | `patient_level_data` | `kol_interview` | `experiment` | `cmc_diligence` | `ip_diligence`.

## Bundle

```json
{
  "bundle_id": "B-...",
  "run_id": "R-...",
  "version": 1,
  "as_of": "2026-10-06",
  "content_hash": "sha256:...",
  "catalog": ["<allowed URLs and IDs fetched in this run>"],
  "created_at": "..."
}
```

### Content hash

`content_hash` is `sha256:` plus the SHA-256 of a canonical JSON (sorted keys, no spaces, UTF-8) of:

- all evidence sorted by `id`, every field except `retrieved_at` and `version`;
- `section_statuses`.

Identical evidence therefore gives an identical hash regardless of when it was fetched or in what order. `as_of` and the bundle `version` are not hashed. Evidence `id` is hashed on purpose: claims reference ids, so bundles whose ids differ must not share a hash (and a cached LLM answer). Implementation: `bioverdict.store.bundle.compute_content_hash`.

## Resolver output

```json
{
  "indication": { "name": "", "mondo_id": "", "efo_id": "" },
  "targets": [{ "symbol": "", "uniprot": "", "ensembl": "" }],
  "action": "agonist | antagonist | inhibitor | degrader | knockdown | upregulation",
  "modality": "small molecule | antibody | siRNA | ASO | peptide",
  "delivery": "oral | SC | IV | intrathecal",
  "tissue": "",
  "known_assets": [],
  "assets": [{ "name": "DIVARASIB", "chembl_id": "CHEMBL5095236" }],
  "assumptions": ["fields the system inferred itself"]
}
```

Several targets are allowed (a triple agonist has three; a degrader and a knockdown need different genetic logic).

`known_assets` are the names to search registries with (what the user typed and the database name). `assets` are the drugs a database identified, each with its ChEMBL id; `chembl_id` is `null` when no database confirmed the name, and a model never writes it. Ids of targets and diseases follow the same rule: they come from Open Targets lookups, not from a model.

## Verdict result: claim ids on top risks (accepted by Dasha, 2026-10-10)

> **Status: accepted and implemented.** Dasha accepted option B and decided that the usual
> approval by Arsenii before the code (`CONTRIBUTING.md`, "Schema changes") is not needed for
> this change; Arsenii reviews it in the pull request. The change is additive and forward-only.

`VerdictResult` (`store/models.py`, stored in `runs.result_json`, served as `ExecutiveVerdict`)
has `top_risks: list[str]`, at most 3. A string cannot say which claim a risk comes from, so the
Report cannot link a risk to its claim and the claim's quote. Today the strings are gate texts and
weak key claims only (`scoring/verdict.py`), so a run's "top risks" are the same texts as its
gates ("A link of the human translation chain is missing"), and claims that an investor would
name as risks (`implication = unfavourable`) never reach them.

### 1. The field

Add one field to `VerdictResult` and `ExecutiveVerdict`:

```json
{ "top_risks": ["..."], "top_risk_claims": [["C-0107"], ["C-0011", "C-0052"], ["C-0070"]] }
```

`top_risk_claims[i]` lists the claim ids that risk `i` rests on (at least one for every risk).
It is empty or exactly as long as `top_risks`; a validator enforces that.

- **Why a parallel list, not a list of `{text, claim_ids}` objects.** `top_risks: list[str]` is
  read by the eval runner (Jaccard stability and `match_risks`), the Report schema and every
  stored run. An additive field leaves all of them working; changing the element type breaks them.
- **Compatibility.** `default_factory=list`, so a stored `result_json` without the field loads and
  shows risks without links. The models use `extra="forbid"`, so code before this change cannot
  read a result written after it: this is forward-only, as every earlier additive field was.
  `result_json` is a JSON blob: **no SQLite migration, no `schema_version` bump**.

### 2. Selection rule

A candidate risk is one of: a fired hard gate, a fired soft gate or unconfirmed kill criterion
(claim ids: the gate's `claim_ids`); a key claim below the key-claim bar (as before, claim id:
itself); an `unfavourable` claim (claim id: itself). An `unfavourable` claim is a candidate when
it pulls its module **against** investing: `contribution(claim) < 0`, the same pull the module
answers use (`scoring/pull.py`; `-(2 * confidence - 1)` for an `unfavourable` claim, `0` for
`unknown`, `hypothesis`, a neutral claim or a claim without weighted evidence). Its weight is
`-contribution`. Confidence already carries the level weights (`confidence_parts`), so no second
weight is added. A refuted unfavourable claim (confidence below 0.5) has a positive pull and is not
a risk.

**Option B (chosen).** Fired hard gates first (a kill criterion is always the top risk); then
unfavourable claims by weight; then the soft gates, the unconfirmed kill criteria and the key
claims below the bar, which fill what is left. Option A (gates first, claims after) was rejected:
on a run like the BTK x multiple sclerosis run of 2026-10-10 (soft gates S1 and S2 plus one weak key
claim) it fills all three slots from gates and shows no claim-derived risk. The soft gates stay
in the gates list and in "What would change our mind", where they say what holds the verdict at
Conditional.

Also: at most 3 risks; ties on weight go to the higher confidence, then the claim id; a result
restated by several claims is listed once: a claim whose evidence shares an independence group
(the trial or publication family) with a risk already chosen is skipped, and when a claim's groups
are not known (the verdict scored without its links), one claim-derived risk per section stands
in; a claim-derived risk's text is the claim's own text. No candidate at all: `top_risks` is empty
and the Report says "No risk was ranked", as before.

### 3. What the API and the Report do

`ExecutiveVerdict` gains `top_risk_claims` with the same meaning. The Report shows each risk with
its claim ids as links to the claim in "Claims and their evidence" (opened), whose drill-down
already goes on to the verbatim quote and the source link. A risk without claim ids (an old
stored run) is shown as text, as now. `docs/scoring.md` ("Verdict mapping" and "What would change
our mind") and the Report documentation are updated in the same PR as the code.

### 4. Questions that were open

1. Option A or B: B (above). The eval cases' `expected_top_risks` should be re-read against it.
2. One result restated by several modules: decided by independence group (above), which is the
   notion of independence the confidence formula already uses.
3. `contribution` moved from `module_answers.py` to `scoring/pull.py`, so `verdict.py` and
   `module_answers.py` both import it without a cycle.

## Verdict result: the written theses (accepted by Dasha, 2026-10-10)

`VerdictResult.theses: list[Thesis]` (additive, `default_factory=list`; no SQLite migration, as
`result_json` is a JSON blob). Served as `ReportResponse.theses`.

```json
{ "theses": [ { "kind": "scientific",
                "sentences": [ { "text": "...", "claim_ids": ["C-0001", "C-0003"] } ] } ] }
```

- `kind` is one of `scientific`, `translation`, `development_plan`, `competitive`, `commercial`,
  `investment` (`ThesisKind`, in report order), at most once each.
- A sentence has at least one claim id of the run; at most four sentences a thesis.
- Written by the synthesis step (`docs/architecture.md`, stage 6a) and grounded by code: a
  sentence that cites no claim of the run, or holds a number found neither in its cited claims
  nor in the figures code computed, is dropped. It is inference over claims, not evidence: no
  claim, gate or score reads it.
- A stored older run, or a run whose synthesis step failed, has `[]`.

## SQLite schema (sketch)

```sql
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, input_json TEXT, as_of TEXT, status TEXT,
  verdict TEXT, created_at TEXT, finished_at TEXT, schema_version INTEGER,
  resolver_json TEXT, result_json TEXT
);
CREATE TABLE run_events (
  run_id TEXT, seq INTEGER, step TEXT, status TEXT, detail TEXT, created_at TEXT,
  PRIMARY KEY (run_id, seq)
);
CREATE TABLE bundles (
  bundle_id TEXT PRIMARY KEY, run_id TEXT, version INTEGER,
  content_hash TEXT, as_of TEXT, catalog_json TEXT, section_statuses_json TEXT,
  created_at TEXT, UNIQUE (run_id, version)
);
CREATE TABLE evidence (
  run_id TEXT, id TEXT, source TEXT, source_family TEXT, source_kind TEXT,
  type TEXT, url TEXT, locator_json TEXT, excerpt TEXT, published_at TEXT,
  retrieved_at TEXT, level TEXT, independence_group TEXT, version INTEGER,
  status_key TEXT,
  PRIMARY KEY (run_id, id)
);
CREATE TABLE claims (
  run_id TEXT, id TEXT, section TEXT, claim_type TEXT, text TEXT, basis TEXT,
  status TEXT, confidence REAL, confidence_parts_json TEXT, flags_json TEXT,
  depends_on_json TEXT, diligence_type TEXT, chain_link TEXT,
  gate_signals_json TEXT, critical INTEGER, version INTEGER, implication TEXT,
  PRIMARY KEY (run_id, id)
);
CREATE TABLE claim_evidence (
  run_id TEXT, claim_id TEXT, evidence_id TEXT, direction TEXT, quote TEXT,
  PRIMARY KEY (run_id, claim_id, evidence_id)
);
CREATE TABLE llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, step TEXT, provider TEXT,
  model TEXT, effort TEXT, input_tokens INTEGER, output_tokens INTEGER,
  cost_usd REAL, latency_ms INTEGER, attempts INTEGER, cache_hit INTEGER,
  failover_from TEXT, error TEXT, created_at TEXT
);
CREATE TABLE http_cache (
  key TEXT PRIMARY KEY, url TEXT, body BLOB, fetched_at TEXT
);
CREATE TABLE verification_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, claim_id TEXT,
  check_name TEXT, passed INTEGER, detail TEXT
);
```

Use WAL mode. One database file per developer; share demo state as a dump.

Notes:

- Ids such as `E-0001` and `C-0001` are unique only within a run, so evidence, claims and their links use the composite key `(run_id, id)`.
- A bundle has no evidence table of its own. Bundle version `N` of a run contains every evidence row of that run with `version <= N` (evidence is append-only).
- The applied migration level is stored with `PRAGMA user_version`; `runs.schema_version` records the level a run was created under.
- `runs.resolver_json` holds the `ResolverOutput` (with its assumptions) and `runs.result_json` the `VerdictResult` of a finished run; `runs.verdict` repeats the verdict word for listings. `run_events` is the progress log of a run (one row per step and status); the SSE endpoint streams it and the trace panel reads it.
