# LLM experiment registry

## Implemented variants

1. **Quantitative baseline:** frozen deterministic BTC 24-hour momentum; decision logic unchanged.
2. **LLM veto:** may turn a baseline `buy` into `hold`; cannot create a trade, modify a sell, or increase size. Failure/abstention preserves the baseline.
3. **LLM-derived features:** schema-validated sentiment, relevance, novelty, severity and uncertainty for later chronological ML training.
4. **Constrained LLM agent:** research proposal only; eligible assets, 60% schema maximum, long-only ownership checks, and `order_submitted=false`.
5. **Non-LLM NLP:** deterministic zero-cost lexicon control plus an optional local-files-only ProsusAI FinBERT adapter.

## Provider matrix

| Provider | Protocol | Credential behavior |
|---|---|---|
| OpenAI | Responses API, strict `text.format` JSON Schema | `OPENAI_API_KEY`, server only |
| Anthropic | Messages API, forced schema tool input | `ANTHROPIC_API_KEY`, server only |
| OpenAI-compatible | Chat Completions JSON schema | Configured server environment variable |
| Ollama/local | Local OpenAI-compatible endpoint | No key required |

Configuration includes model, endpoint, temperature, timeout, retries, tokens, per-cycle requests, daily/monthly caps, prices, frequency and prompt version. The default monthly cap is $5; all analysis defaults disabled.

## Executed evaluation

- Real provider decisions: **0**.
- Historical LLM decisions: **0**.
- Successful mock provider response fixtures used for engineering verification: **4** (two service paths and two HTTP protocol paths); these are not market or profitability evidence.
- Focused automated tests: **22 passed** covering provider config, missing keys, schemas, malformed outputs, injection containment, budgets, cache, timestamp integrity, veto behavior, fail-open API behavior, features, proposal limits, shadow recording, API mode separation, dashboard, and frozen baseline.

No credentials were present or requested. `research/llm/experiments.json` is the machine-readable registry.
