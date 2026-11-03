# LLM final recommendation

## Decision

**Do not adopt LLM augmentation as a trading strategy yet. Retain the quantitative baseline and begin prospective shadow evaluation.**

The integration is operationally ready for credentialed research, but there is no scientifically valid historical LLM performance experiment because the repository lacks point-in-time news and cached genuine model outputs. Running modern models on identifiable old events would mix historical memorization with signal quality.

## What is proven

- The +2.6338% baseline reproduces exactly and remains unchanged.
- OpenAI, Anthropic, OpenAI-compatible and local Ollama protocols are configurable without source edits.
- Missing keys, disabled analysis, provider failure, bad JSON and exhausted budgets cannot block the baseline.
- LLM outputs are schema validated, logged and isolated from broker/order code.
- Vetoes can only remove entries; agent proposals remain research records.
- Point-in-time news availability, deduplication, caching, cost accounting and prospective shadow persistence work under automated tests.

## What is not proven

- Any LLM model improves return, drawdown or trade selection.
- FinBERT or LLM sentiment predicts this BTC strategy.
- API latency and costs are justified by a $500 account.
- Results persist out of sample.

Keep `enabled=false` until a provider/model and explicit research budget are selected. Never promote from shadow mode until the gates in `LLM_PERFORMANCE_COMPARISON.md` are met.
