# Final strategy recommendation

## Decision

**NO QUALIFIED PROFITABLE STRATEGY FOUND.**

Keep autonomous real-money trading disabled. Keep the new strategies available only as research candidates and local simulations.

## Strongest candidates

1. **Simple 24-hour BTC momentum comparator:** +2.63% in the final three-month period over 29 trades, but -8.19% drawdown, $27.19 modeled costs, 17.2% win rate, and 1.20 profit factor. It underperformed true 60%-deployed BTC buy-and-hold (+13.75%) and used nearly the full active-policy drawdown buffer. This is not qualified.
2. **Cost-aware hourly XGBoost:** best ML development screen (+3.22%) came from one trade. Rolling tests produced one losing trade and three cash folds; final holdout had zero trades. This is unvalidated, not profitable evidence.
3. **Equity ORB adaptation:** -1.18% over 25 trades and worsened monotonically with costs. The available equity dataset is too narrow and short for the published approach.

Neither additional comparator changes the decision: 60%-deployed ETH buy-and-hold returned +12.42% with -14.60% drawdown, while simple BTC mean reversion lost 4.83%. SPY buy-and-hold lost 1.63% in the narrow equity sample; ORB beat it slightly but remained negative.

## What is proven

- Next-open, leakage-controlled XGBoost research and complete signal diagnostics work.
- Cost-aware filtering reduces activity and prevents trading forecasts too small for retail costs.
- The $500 account can execute fractional crypto and equity orders without leverage.
- Regime and volatility-sizing ablations are reproducible.
- None of these facts establishes an economic edge.

## What remains unproven

- Positive net return with an adequate independent trade sample.
- Performance better than passive exposure.
- Stability across regimes.
- Robustness on the same trade set to moderately worse execution.
- Prospective paper performance over at least 12 weeks.
- ORB performance on a broad, survivorship-free 5-minute U.S. equity universe.
- Account-specific exchange/broker fees, spread, slippage, and regional eligibility.

## Next research gate

Freeze the current code and collect genuinely new forward data. Do not tune on the 2024-2026 archive again and call the result fresh. Reconsider a strategy only after it has:

- at least 100 completed historical exits and 30 prospective paper exits;
- positive net and 2x-cost performance;
- positive lower confidence bound on weekly return;
- drawdown below 8%;
- positive performance in multiple regimes;
- benchmark outperformance meaningful enough to justify operational complexity.

Until then, the correct allocation is cash or a separately chosen passive investment—not autonomous active trading based on these models.
