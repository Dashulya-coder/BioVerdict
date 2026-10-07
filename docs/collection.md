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

Per section: at most 8 logical connector fetches, 90 seconds, and one logical extraction
call per nonempty fetch. Per fetch: at most 50 records and 24,000 source characters.
Extraction proposes at most 32 facts; hitting that capacity is conservatively incomplete.
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

Auth/configuration failures propagate instead of becoming a successful empty result.
Collection issues name tools and exception classes without copying provider exception bodies.
The staged trace is returned; durable collection-event/API trace wiring is later integration.
Real LLM calls use the existing logger. Cancelling a sync worker cannot terminate its provider
call; live callers must configure provider timeouts and run deadlines. No late result is
accepted into the timed-out section.

Checkpointing, live connector registration, full reason/score/verify/report wiring and the
API/CLI lifecycle remain subsequent work. Tests verify the offline boundary and mocked call
logging; they do not establish live-provider or medical extraction quality.
