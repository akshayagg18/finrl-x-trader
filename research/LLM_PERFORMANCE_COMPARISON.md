# LLM performance comparison

## Measured results

| Variant | Genuine decisions | Net trading P&L | API cost | Incremental net value | Status |
|---|---:|---:|---:|---:|---|
| Quantitative BTC momentum baseline | Deterministic historical run | +$13.17 (+2.6338%) | $0 | Control | Reproduced |
| Quantitative + LLM veto | 0 | Not measured | $0 | Not measurable | Prospective only |
| Quantitative + LLM features | 0 | Not measured | $0 | Not measurable | Prospective only |
| Constrained LLM agent | 0 | Not measured | $0 | Not measurable | Prospective only |
| Quantitative + non-LLM sentiment | 0 | Not measured | $0 | Not measurable | Prospective only |

No model was actually called. Mock responses validate software behavior only and are excluded from performance. Therefore veto rate, false-veto rate, latency, tokens, cost, confidence intervals and after-API returns are currently undefined—not zero.

The paired-veto evaluator is implemented and reports avoided losses, missed profitable trades, false-veto rate and net veto value once opportunities settle. Incremental net value is calculated as LLM-strategy P&L minus baseline P&L minus incremental API/data cost.

## Required prospective gate

Collect at least 100 baseline opportunities and 30 completed LLM-affected trades across multiple regimes. Freeze provider, model, prompt and thresholds before evaluation. Adoption requires positive paired incremental value after API cost, a confidence interval that does not depend on one or two trades, and no risk-control bypass.
