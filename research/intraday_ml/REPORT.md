# Machine-learning evaluation — 2026-11-03

**NO QUALIFIED LIVE STRATEGY.** Models were built and tested; consistent after-cost profitability was not demonstrated.

Random forest and histogram gradient boosting regress future open-to-open returns. Inputs are lagged returns, realized volatility, rolling deviations, range, volume and time-of-day. All labels mature before training cutoff; random train/test splitting is prohibited. An expected-return threshold includes round-trip fees, adverse execution and a selected extra buffer. Horizon/cooldown rules limit turnover.

Selection: train before 2025-07-01; validate July–August 2025. Eight configurations per symbol/interval (2 families × 2 horizons × 2 buffers), 32 validation scenarios total. Lock highest validation return subject to observed drawdown better than -15%, then refit that family/horizon before each subsequent test. Four symbol/interval combinations × 3 test windows × 7 scenarios = 84 walk-forward backtests, **116 evaluations total**.

Each fold starts independently with $500; default deployment ceiling 50%, 10 bps fee + 5 bps adverse execution per side. These are global spot research assumptions, not a verified Singapore account tariff. Holding cash earns no interest. Hold comparisons invest the same 50%, bypass stops, and liquidate at period end. USDT/USD parity is assumed.

| Market | Interval | Jan–Feb 2026 ML | Jul–Aug 2026 ML | October 2026 ML | Fills across folds |
|---|---:|---:|---:|---:|---:|
| BTC-USDT | 5m | -1.490% | +0.293% | +0.000% | 18 |
| BTC-USDT | 15m | +0.032% | +0.000% | +0.000% | 16 |
| ETH-USDT | 5m | -0.670% | +0.000% | +0.000% | 18 |
| ETH-USDT | 15m | -3.791% | -0.388% | +0.000% | 34 |

All selected models placed zero October trades. That is abstention, not a profitable trading result. The small positive BTC periods had few fills and do not establish an edge. Avoid tuning again on these results and presenting the same periods as untouched.

October baseline performance was already inspected in earlier work; it is excluded from model fitting/selection but is **not a pristine research holdout**. These are retrospective tests, not prospective paper profits. The much shorter equity history is not used to claim an equity ML advantage.

Full net/gross/1.5×/2× costs and cash/hold/momentum comparisons: [comparison.csv](comparison.csv). Compressed JSON files contain actual execution fills and equity curves. Per-exit statistics, fees, turnover, holding time, downside metrics and worst losing streak: [analytics.csv](analytics.csv). Risk ratios use daily observations, not inflated intrabar annualization. Yearly returns are omitted for short periods. Gross scenarios are independently rerun, so costs can change sizing and halt behavior.

Models and frozen data are content-hashed. Runtime model artifacts stay local, outside Git; recreate with `python -m scripts.benchmark_ml`, or train/select versions through the dashboard. Only locally created hash-verified artifacts may be loaded. `environment.json` records package versions.

## Continuous simulation and remaining external gates

The existing scheduler now advances isolated, persistent historical replay sessions. Nautilus preserves continuous holdings through deterministic reconstruction without cycle-end liquidation. Atomic SQLite cycles and fill identities prevent duplicate saved trades. Pause blocks entries while stops/exits continue; Stop suspends monitoring; liquidation runs at the next simulated bar. This accelerated replay is neither a streaming market-data paper account nor a brokerage account.

The shared portfolio-loss gate covers daily, peak and initial-capital losses. Equity sale proceeds are withheld until the next exchange session; original settled cash remains usable. Single-instrument sessions have immutable configuration and isolated virtual capital. Sessions do not share funds with existing swing strategies or manually held assets.

The CCXT OKX spot transport implements balances, positions, instruments, quotes, order lookup/cancellation/fills and guarded market submission. Missing credentials, regional verification and authorization fail closed. Transport timeouts are ambiguous and never retried automatically. It is **not wired to the intraday live scheduler**, and Singapore account eligibility/endpoint plus broker-reported fills remain externally unverified. Full multi-market live risk/ownership routing and fractional equity execution remain unfinished implementation. No real orders were submitted.

Recommendation: retain cash/default-disabled live trading. Use the completed replay and training tools to conduct predeclared new experiments or a prospective paper study; do not present any tested model as proven profitable.
