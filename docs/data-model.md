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

`level` values, strongest first: `human_genetics`, `human_interventional`, `human_observational`, `animal_in_vivo`, `in_vitro`.

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
  "confidence_parts": { "support": 0.82, "contra": 0.10, "freshness": 0.95 },
  "depends_on": ["C-0102"],
  "diligence_type": null
}
```

Link:

```json
{ "claim_id": "C-0117", "evidence_id": "E-0042", "direction": "supports", "quote": "verbatim, must occur in the evidence excerpt" }
```

`claim_type` (`target_causal` | `drug_acts_in_humans` | `other`) selects the column of the level-weight table in [`scoring.md`](scoring.md). `flags` holds `sparse`, `contested`, `missing_link`. `chain_link` (`molecular_effect` | `human_exposure` | `target_engagement` | `biological_response` | `patient_benefit`) places a claim on the translation chain. `gate_signals` lists the gates (`K1`..`K5`, `S1`..`S6`) whose condition the claim asserts; code decides whether the gate fires. `critical` marks key claims for the verdict.

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
  "assumptions": ["fields the system inferred itself"]
}
```

Several targets are allowed (a triple agonist has three; a degrader and a knockdown need different genetic logic).

## SQLite schema (sketch)

```sql
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, input_json TEXT, as_of TEXT, status TEXT,
  verdict TEXT, created_at TEXT, finished_at TEXT, schema_version INTEGER
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
  PRIMARY KEY (run_id, id)
);
CREATE TABLE claims (
  run_id TEXT, id TEXT, section TEXT, claim_type TEXT, text TEXT, basis TEXT,
  status TEXT, confidence REAL, confidence_parts_json TEXT, flags_json TEXT,
  depends_on_json TEXT, diligence_type TEXT, chain_link TEXT,
  gate_signals_json TEXT, critical INTEGER, version INTEGER,
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
