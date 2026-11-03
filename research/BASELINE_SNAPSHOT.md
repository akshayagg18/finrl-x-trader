# Frozen positive baseline

The positive control is the deterministic **BTC-USDT 24-hour momentum comparator**, not an LLM and not the zero-trade XGBoost selection. Commit `7281adc` and `research/llm/baseline_snapshot.json` freeze its evidence.

| Field | Frozen value |
|---|---:|
| Data | OKX BTC-USDT spot, SHA-256 `207cbd...e5c6ea2` |
| Bar / lookback | 1 hour / 24 hours |
| Evaluation | 2026-08-01 through 2026-10-31 UTC |
| Capital / exposure | $500 / maximum 60% |
| Costs | 10 bps fee + 5 bps adverse execution per side |
| Net P&L / return | +$13.17 / +2.6338% |
| Maximum drawdown | -8.1929% |
| Trades / costs | 29 / $27.19 |
| Sharpe / Sortino | 0.796 / 1.772 |
| Win rate / profit factor | 17.24% / 1.202 |
| Seed | None; rule is deterministic |

The result was reproduced before LLM code changes by recomputing the baseline from the frozen CSV and comparing all key metrics to `research/profitability/summary.json`. It is positive, but it is **not qualified**: it underperformed 60%-deployed BTC buy-and-hold by 11.11 percentage points and nearly consumed the active 8% drawdown budget.

The baseline path is unchanged. LLM failures explicitly fall back to it, and LLM code has no broker or order-routing imports.
