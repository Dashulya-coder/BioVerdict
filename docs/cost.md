# Models, pricing and cost per run

Prices below were read from the providers' official pricing pages on 2026-10-06. Prices and promotions change: re-check before every cost report. Do not quote numbers from this file in the README without re-verifying.

## Official list prices (USD per 1M tokens, input / output)

| Provider | Model | Price | Notes |
|---|---|---|---|
| Anthropic | Claude Fable 5.1 | 10 / 50 | not planned |
| Anthropic | Claude Opus 5.5 | 4 / 20 | optional for one control run |
| Anthropic | Claude Sonnet 5.5 | 2 / 10 | reasoning steps, Skeptic, Chair, synthesis |
| Anthropic | Claude Haiku 4.5 | 1 / 5 | extraction |
| Google | Gemini 3.8 Flash | 0.75 / 3.75 through 2026-12-31, then 1.50 / 7.50 | failover, judge |
| Google | Gemini 3.5 Flash-Lite | 0.30 / 2.50 | extraction, failover |
| Google | Gemini 3.1 Pro Preview | 2 / 12 (4 / 18 above 200k prompt tokens) | preview status |
| OpenAI | gpt-6-astra | 10 / 50 | not planned |
| OpenAI | gpt-6.1-sol | 2 / 10 | failover, judge |
| OpenAI | gpt-6-luna | 0.10 / 0.50 | extraction candidate, gated |

- Batch APIs give 50% off but are asynchronous: use for evaluation runs, not for the live demo.
- Prompt-cache reads are much cheaper than uncached input.
- Anthropic's newer tokenizer (Opus 4.7 and later, Sonnet 5.x) produces about 30% more tokens for the same text.
- Gemini 4 Argon was announced on 2026-09-30 but is not generally available through the API; do not plan on it.

Sources: https://platform.claude.com/docs/en/about-claude/pricing, https://ai.google.dev/gemini-api/docs/pricing, https://developers.openai.com/api/docs/pricing

## Important: cost per task is not price per token

Reasoning effort dominates the bill. Independent measurements (Artificial Analysis, https://artificialanalysis.ai/models/releases/comparisons/claude-sonnet-5-5-vs-gemini-3-8-flash) report for Claude Sonnet 5.5: roughly $0.42 per benchmark task at low effort, $0.59 at medium, $1.12 at high and $7.67 at max, with a time to first token of about 450 seconds at max. Gemini 3.8 Flash was about $0.93 at medium and $1.24 at high. Consequences:

1. Use **medium or high** effort for reasoning steps, **never max** (too slow for the live demo).
2. Use **no reasoning / low** for extraction.
3. Budget by measured cost per run, not by price per token.

## Model roles

| Step | Primary | Failover | Effort |
|---|---|---|---|
| Resolver | Haiku 4.5 | Gemini 3.5 Flash-Lite | none/low |
| Extraction (quote + value) | Haiku 4.5 | gpt-6-luna, Gemini 3.5 Flash-Lite | none/low |
| Reasoning modules | Sonnet 5.5 | gpt-6.1-sol, Gemini 3.8 Flash | medium-high |
| Entailment judge | model from a different provider than the generator | | medium |
| Skeptic / Chair / synthesis | Sonnet 5.5 | gpt-6.1-sol | high |
| Baseline ("bare LLM") | all three providers, no retrieval | | |

These are starting hypotheses. The final assignment comes from the bake-off below.

Why Sonnet 5.5 rather than Opus 5.5 for the strongest steps (hypothesis to confirm): third-party tracking reports a closed-book "hallucination rate" of about 47% for Sonnet 5.5 against about 59% for Opus 5.5 on AA-Omniscience, with Opus ahead on factual accuracy. In a closed-world pipeline we want the model that guesses less and follows instructions, not the one that knows more. These are general benchmarks, not our task.

## The hackathon gateway (OpenAI-compatible)

The organizers give each team a key for an Azure-hosted, OpenAI-compatible gateway (set
`TEAM_API_KEY` and `LLM_BASE_URL`; `LLM_PROVIDER=openai` forces it). Models: `gpt-6-luna`,
`gpt-6.1-sol`, `gpt-6-astra`, `gpt-5-mini` (from `/v1/models`). Probed on 2026-10-09:

- **Probed again on 2026-10-10 (evening), small requests on each model:**
  - *Request size:* no limit seen. `gpt-6.1-sol` took 128,000 characters, `gpt-6-astra` 32,000
    (larger not tried), `gpt-6-luna` 256,000; 512,000 on `gpt-6-luna` was a 502, probably the
    model's own context. The preset therefore sets no request limit (below).
  - *Output:* `max_completion_tokens` of 4,096 is accepted and 4,097 refused, now with a 502
    `upstream_error` rather than a 400.
  - *Concurrency:* three requests are served at once. Of 8, 4, 4 and 3 sent together, 3 were
    answered each time and the rest refused with `429 concurrency_limit`. The key is the team's,
    so a request from another process takes a slot too. `LLM_MAX_CONCURRENCY` defaults to 3.
- **A limit counted the request as it travels**, JSON-encoded and in UTF-8 bytes (measured
  2026-10-10, while the size limit below was in force): a quotation mark or a line break counts 2,
  an accented letter 2, a symbol such as the 'greater than or equal' sign 3
  (`llm/sizing.py: wire_len`, used by the adapter and by every prompt builder).
- Chat completions only. Structured output by `response_format` json_schema in strict mode works,
  and so do a system message, `max_completion_tokens` and `reasoning_effort`.
- `temperature` and the old `max_tokens` are answered with a **502, and the gateway charges a
  reserved amount for that failed request**. The adapter never sends them.
- **On 2026-10-09 a request could be at most about 16,180 characters** (the text of every
  message, plus the response schema as compact JSON, plus about 100 of the gateway's own); a
  longer one was refused with `400 Input exceeds the conservative input limit`. It was gone on
  2026-10-10 (above). `LLM_MAX_INPUT_CHARS=16000` puts it back: the client then refuses a larger
  request before it is sent (`InputTooLargeError`, no cost).
- **What sizes a prompt now is the answer.** The answer grows with what the prompt holds, and
  must stay under 4,096 tokens (`StepConfig.prompt_chars`): more evidence means more batches, not
  larger ones. The Chair gets 60,000, room for every claim of a run. The judge sizes its own batches (14,000 characters of items, a passage of up to 2,000
  characters around each quote instead of 450). `LLMClient.input_budget` gives each step the
  smaller of its own size and the endpoint's limit.
- **Sizes after the first run without the limit** (`R-cf6f3be64e7b409f803f162134a0f174`): a
  clinical batch of 16,000 was cut off at 4,096 tokens and retried short, so the clinical module
  gets 12,000 (and a module up to four batches instead of three); the Skeptic wrote 3,881 tokens
  from 60,000 and gets 30,000; the judge wrote 3,367 from 24,000 of items and gets 14,000.
- **Sizes after the second run** (`R-e0a3a432b1a6486da63da74805af1a04`): a translation batch of
  16,000 was cut off too, so every module and the classification of new evidence get 12,000
  (`GATEWAY_MODULE_CHARS`, up to four batches); extraction keeps 16,000 (its answers stayed under
  900 of 3,000 tokens). The Skeptic wrote 1,532 tokens from 30,000 and grounded 1 objection
  (5 from 60,000), and gets 45,000. The judge's largest answer was 2,220 tokens.
- The adapter sends a schema without `title` and `description` (the `ModuleDraft` schema is 1.6
  thousand characters instead of 2.8).
- Reasoning models spend hidden reasoning tokens inside `max_completion_tokens` (they are billed
  as output), so the gateway preset keeps the limits tight (3,000 for extraction, 4,096 for
  reasoning and synthesis). **The gateway refuses `max_completion_tokens` above 4,096**
  (4,000 accepted, 5,000 refused with `400 Output token limit is outside the supported range` on
  2026-10-09, on all three models; 4,097 refused with a 502 on 2026-10-10), so no step can ask
  for more.
- Roles used by the preset (`LLMConfig.for_provider("openai")`): resolver and extraction on
  `gpt-6-luna`; reasoning, classification of new evidence and synthesis on `gpt-6.1-sol`, with
  `gpt-5-mini` as the second model. `gpt-6-astra` costs five times `gpt-6.1-sol` and is not used.
- The gateway has one vendor's models only, so a judge "from a different provider" (B8) cannot be
  had from it alone. The `judge` step runs on `gpt-6-astra` (the strongest model, not the one that
  writes the claims; `gpt-5-mini` second) and, when an Anthropic key is also set, on Opus instead
  (the claims stay on the gateway). A run's trace says which model judged. A claim and its quotes
  are a few hundred characters, so a run's judge calls cost a few cents even on `gpt-6-astra`.
- Prices in `GATEWAY_PRICES` are the list prices above; `gpt-5-mini` is a public list price not
  checked against the gateway. The gateway bills its own reserved amounts: compare a run's
  `llm_calls` cost with the portal after the first runs.

## Bake-off (one evening)

1. Collect 20 real documents (ClinicalTrials.gov records, PubMed abstracts, an SEC exhibit).
2. Extraction on each candidate (Haiku 4.5, Gemini 3.5 Flash-Lite, Gemini 3.8 Flash low, gpt-6-luna). Measure: quote verbatim in text, number correct, invalid-JSON rate, tokens, latency, cost.
3. Reasoning steps (module, Skeptic) on Sonnet 5.5 medium and high, gpt-6.1-sol, Gemini 3.8 Flash high. Add one Opus 5.5 control. Score manually.
4. Entailment: one judge per provider against a manually labelled set of about 30 claims.
5. Pick the cheapest model that passes the gates for each step.

Results table: TODO.

## Per-run cost estimate

Placeholder assumptions (not measured; **lower bound**, because reasoning tokens are not counted):

| Stage | Input (M tokens) | Output (M tokens) |
|---|---|---|
| Resolver | 0.01 | 0.002 |
| Extraction (~150 docs of ~6k tokens) | 0.90 | 0.12 |
| Reasoning modules | 0.40 | 0.03 |
| Skeptic / Chair | 0.08 | 0.004 |
| Entailment judge (~200 claims) | 0.20 | 0.02 |
| Synthesis and diligence questions | 0.13 | 0.011 |
| **Total** | **~1.72** | **~0.19** |

Kept as the estimate made before any run; measured numbers are below.

## Measured results

Whole live runs of BTK inhibitor x multiple sclerosis on 2026-10-10, on the organizers' gateway
(`gpt-6-luna` extracts, `gpt-6.1-sol` reasons, `gpt-6-astra` judges). One question: these numbers
describe it, not the system in general, and the runs were made on successive code versions.

| Runs | Cost | Time | Source |
|---|---|---|---|
| Three runs (Arsenii) | $0.90 to $1.20, the last $0.99; the judge about 60% | 3 min 45 s, 7 min 21 s (lost its Chair step to the old 420 s limit), 5 min 7 s | #105 |
| `R-20261010-125211-cf5016` (Dasha) | $0.87 | 6 min 20 s | `llm_calls`, `runs` |
| The run of [`eval.md`](eval.md), section 9 (Dasha) | $0.99 | 357 s | `eval.md` |

Not measured: a median or p90 over repeated runs of one code version, other questions, the
cache hit rate of a warm run (every call above was answered afresh) and failover (none occurred).

Cost by step of `R-20261010-125211-cf5016` (35 calls, 118 k input and 35 k output tokens, no
cache hits, no failover):

| Step | Calls | Input tokens | Output tokens | Cost | Share |
|---|---|---|---|---|---|
| judge | 6 | 17,708 | 5,775 | $0.466 | 53% |
| reasoning (six modules) | 16 | 63,547 | 21,897 | $0.346 | 40% |
| chair | 1 | 4,059 | 2,732 | $0.035 | 4% |
| skeptic | 1 | 4,376 | 1,293 | $0.022 | 2% |
| extraction | 10 | 27,565 | 2,784 | $0.004 | 0% |
| resolver | 1 | 430 | 160 | $0.000 | 0% |

The estimate above assumed about fifteen times as many input tokens (1.72 M) as this run used.

```sql
SELECT run_id, SUM(cost_usd) AS usd, SUM(input_tokens) AS tin, SUM(output_tokens) AS tout
FROM llm_calls GROUP BY run_id;
```

## Budget plan

- Development and debugging: free tiers where available (note: free tiers may use content to improve products; our inputs are public).
- Paid credit only for: bake-off, judge, baseline, final showcase runs.
- Cache everything: LLM responses by hash, HTTP responses by key, frozen bundles by hash.
- Per-run hard cap: `RUN_BUDGET_USD`. A call starts only while the money spent plus the worst case of the calls still under way (whole prompt read, every allowed output token written) is under the cap. Calls of one run are made in parallel, so a run can pass its cap by at most one call, not by all the calls that started together.
- Demo: replay recorded runs from cache; keep one live-capable path as a fallback.

## Consumer subscriptions

Consumer plans (Claude, ChatGPT, Gemini student) do not provide API access. Use them for manual prompt testing and coding assistance only. Do not wrap web sessions in unofficial clients.
