# A4: bounded collection and grounded extraction

This main-based branch implements the standalone collect → freeze boundary. It does not
change shared contracts, Evidence/Bundle models, SQLite schema or the pending API/CLI.
The [LangGraph graph API](https://reference.langchain.com/python/langgraph/graph/state/StateGraph)
runs two named async nodes; section behavior lives in `agents/`, not graph wiring.

## Offline run

From the repository root, with backend dependencies installed:

```bash
uv run --project backend python scripts/collect_fixture.py --db /tmp/a4.sqlite
uv run --project backend python scripts/collect_fixture.py --db /tmp/a4.sqlite --as-of 2000-01-01
```

The first opens a real prepared Divarasib record through FakeConnector/FakeLLM and prints
a newly frozen clinical bundle. The second produces an empty cutoff with none_found for
the queried section. Other sections remain not_searched. Repeating the same run/cutoff
creates another bundle version while preserving canonical IDs and the hash for unchanged
content. No provider keys, external requests or paid calls are needed.

The fixture's old hash is not trusted or validated by this import demonstration (fix #14
remains pending). Every output hash is recomputed by the existing freeze implementation.
This is collection only, not a new underwriting or medical conclusion.

## Integrating the boundary

Construct CollectPlan entries with explicit section/tool names and inject connectors through
CollectNodes. Inject `LLMClient.bind(run_id)` with the existing call logger for live extraction.
Invoke `collection_graph(nodes).ainvoke({run_id, query, as_of})`; its result contains both
the staged collection (including issues, rejected facts and LLM results) and frozen bundle.
Use the same event-loop thread that owns the SQLite connection. Caller owns its lifecycle.

The model returns only source_id, quote and optional value. The code rejects unfetched IDs,
non-verbatim/blank/too-short quotes and incomplete or sign-changed value tokens. Provenance
and strength are copied from retrieval; registry records are never relabelled as efficacy.
Values are verbatim strings retained in staging and the quotation, not calculated decision
numbers or new Evidence fields. Entailment and section relevance still need B8/eval checks.

Cutoff/latest-wins run before prompting. Grounding uses only supplied text, including any
truncated excerpt. Mutable status records remain atomic so multiple extracted spans do not
compete for the same status_key; oversized status records are omitted as incomplete.

## Bounds and failure statuses

Per section: at most 8 logical connector fetches and 90 seconds. Per fetch: at most 50 status
facts and 50 texts, and up to three extraction prompts of 24,000 source characters each (see
below). A prompt returns at most 32 facts; hitting that capacity is conservatively incomplete.
Provider attempts/retries are additionally bounded by the existing LLM client configuration.
Plans execute serially, stop after a global budget/deadline failure, and cannot name tools
outside the injected allowlist. This is a fixed tool loop, not autonomous web research.

| Result | Status |
|---|---|
| No planned tools, unplanned section, or skipped after budget/deadline stop | not_searched |
| All completed queries have no visible records | none_found |
| Visible records read, no requested facts extracted | not_reported |
| Grounded facts with all planned work completed | found |
| Section/run timeout, truncation, rejected fact, capacity/step cap or partial tool failure | incomplete |
| All attempted tools fail, or budget is exhausted before any tool completes | error |

What a connector read only in part (it lists the gaps, for example a study whose posted results
could not be downloaded) is added to the section's issues and makes the section `incomplete`.
Auth/configuration failures propagate instead of becoming a successful empty result.
Collection issues name tools and exception classes without copying provider exception bodies.
The staged trace is returned; durable collection-event/API trace wiring is later integration.
Real LLM calls use the existing logger. Cancelling a sync worker cannot terminate its provider
call; live callers must configure provider timeouts and run deadlines. No late result is
accepted into the timed-out section.

## Answers that are not cached

Source answers are cached without an expiry, so a bad answer stored once would be replayed in
every later run. Each connector therefore checks the shape of a fresh body before it is stored
(`connectors/validate.py`, and the checks of PubMed, Europe PMC, openFDA and Open Targets): an
error object, a maintenance page or a download cut short inside an HTTP 200 answer is refused,
the request fails like any other and the next run asks again. An empty result list is a valid
answer and is cached.

## What is read first

A source often returns more than the limits allow (a drug with many studies gives over 80
registry records; the limit is 50 records and 24,000 characters per source). Records are read in
a fixed order: findings before records that a study exists (evidence level, strongest first),
then the newest, then by id. The limits cut from the end of that order, and the section is still
marked `incomplete`. Posted trial results are therefore read before protocol descriptions.

The target-class search (`clinicaltrials_class`) keeps only the status and the design record of
each study, for up to 12 stopped studies and 12 others, latest phase and newest first. That is
what the competition section needs (phase, status, why a study stopped), and it fits the limit.
Sponsor names are not part of those excerpts; they are in the evidence's independence group.

## Status facts and texts

Within one source, records are of two kinds. A **status fact** (a record with a `status_key`: a
trial's status or design, a database snapshot) is one fact that extraction never cuts, so it goes
to the bundle as retrieved, without a model call. **Texts** (summaries, outcome descriptions,
posted results, abstracts) go to the model, which picks verbatim quotes.

Texts are sent in up to three prompts per source (`max_batches`), at the same time, each with up
to 24,000 characters and up to 32 returned facts. A record that does not fit a prompt is moved
whole to the next one. The 50-record limit holds for each kind separately. Whatever is still
left unread makes the section `incomplete`, as before.

## Live registration

`pipeline/live_sources.py` is the allowlist of a live run: Open Targets and Europe PMC
preprints (`europepmc`) for mechanism,
ClinicalTrials.gov by asset and PubMed for clinical, ClinicalTrials.gov by target within the
indication (`clinicaltrials_class`) and openFDA (`openfda`) for competition. `pipeline/live_run.py` runs the Resolver and
this graph, writes each section's status, fact count, rejections and issues into the `collect`
progress event, and hands the frozen bundle to the shared reason → score step. See the
[runbook](runbook.md) for how to start a live run and how it fails.

The commercial section reads the market sources (`analog_pricing`, `cancer_incidence`,
`cdc_indicators`, `orphanet`, `population`). All of their records are status facts, so no model
reads them; `market/tam.py` computes the market size from them (see [scoring](scoring.md)).

openFDA reads the drugs approved against the same target (the analogs Open Targets names; generic
copies are left out). Approvals, indications and boxed warnings are status facts. The clinical
studies section of each label is text for the model, in verbatim pieces of up to 6,000 characters
cut between sentences. A class with many approved drugs (GLP-1 agonists) has more label text than
the three prompts hold, so its competition section is `incomplete`.

Checkpointing and independent verification (B8) remain subsequent work. Tests verify the offline
boundary and mocked call logging; runs against the real sources used a stand-in model. Neither
establishes live-provider or medical extraction quality.
