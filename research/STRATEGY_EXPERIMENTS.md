# Strategy experiment registry

## Frozen protocol

- Data: genuine OKX BTC-USDT spot, 5-minute source bars, 2024-11-01 through 2026-10-31; SHA-256 retained in `research/profitability/protocol.json`.
- Capital: $500; long-only; no leverage; maximum exposure 60%.
- Costs: 10 bps fee + 5 bps spread/slippage per side; 1.5x and 2x stress.
- Risk: 2% daily new-entry pause, 8% peak drawdown halt, $1 minimum order.
- Passive BTC, ETH, and SPY comparators use the same fractional 60% exposure and costs but intentionally do not inherit active-strategy risk halts.
- Features: lagged log returns, momentum, realized volatility, moving-average distance, ATR ratio, range, close location, volume changes, RSI, and UTC seasonality.
- Timing: completed bar at `t`, simulated fill at open `t+1`, label exit at open `t+horizon+1`.
- Training: XGBoost regression; matured labels only; deterministic seed 17.
- Validation: first half calibrates median absolute forecast error; second half selects hurdle, regime filter, and sizing.
- Selection grid: threshold multipliers 1/2/3 x all/trending regimes x fixed/volatility sizing.
- Screen: 2024-11 to 2025-07 train, 2025-08 to 2025-10 validation, 2025-11 to 2026-07 development OOS.
- Final selected-strategy holdout: 2026-08 through 2026-10. These dates were viewed in earlier strategy work, so this is strategy-level, not pristine-market, holdout evidence.

## Interval and horizon screen

| ID | Bar | Forecast horizon | Development OOS net | Trades | 1.5x cost | 2x cost | Direction accuracy | Spearman |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 5m_to_4h | 5m | 4h | -2.68% | 11 | -4.84% | -4.74% | 48.83% | -0.0148 |
| 15m_to_4h | 15m | 4h | -8.37% | 9 | -7.81% | -7.80% | 49.62% | -0.0016 |
| 30m_to_4h | 30m | 4h | -6.15% | 7 | -5.56% | -6.99% | 50.21% | +0.0131 |
| 1h_to_1h | 1h | 1h | +3.22% | 1 | 0.00% (cash) | 0.00% (cash) | 50.76% | +0.0183 |
| 1h_to_4h | 1h | 4h | -1.63% | 1 | +1.71%* | +1.55%* | 50.60% | +0.0159 |
| 4h_to_4h | 4h | 4h | -6.39% | 4 | +6.20%* | +4.84%* | 50.73% | -0.0420 |

`*` Higher costs changed the hurdle and selected different tiny trade subsets. Baseline loss plus one-to-four trades fails robustness.

No configuration met the predeclared requirement of positive development OOS, positive 1.5x-cost return, and at least 10 trades. The fallback `1h_to_1h` was frozen only so the protocol could diagnose a final candidate; `qualified_at_selection=false` is persisted.

## Selected configuration walk-forward

| Fold test | Net return | Trades | Gross positive candidates | Net candidates | 1.5x | 2x |
|---|---:|---:|---:|---:|---:|---:|
| 2025-11 to 2026-01 | 0.00% | 0 | 1,370 | 0 | 0.00% | 0.00% |
| 2026-02 to 2026-04 | -1.36% | 1 | 916 | 1 | +3.13%* | +3.03%* |
| 2026-05 to 2026-07 | 0.00% | 0 | 1,097 | 0 | 0.00% | 0.00% |
| 2026-08 to 2026-10 final | 0.00% | 0 | 900 | 0 | 0.00% | 0.00% |

Again, `*` is a different one-trade subset, not same-trade cost survival.

## Regime and sizing ablation

Development OOS for the selected hourly screen:

| Regime | Sizing | Net | Drawdown | Trades |
|---|---|---:|---:|---:|
| All | Fixed 60% | +3.22% | -3.11% | 1 |
| Trending only | Fixed 60% | +3.22% | -3.11% | 1 |
| All | Volatility-adjusted | +2.16% | -2.09% | 1 |
| Trending only | Volatility-adjusted | +2.16% | -2.09% | 1 |

No independent filter has enough trades to justify combination or deployment.

## Equity comparison

The 15-minute long-only ORB pilot uses AAPL, SPY, and QQQ, fractional shares, 0.5% risk budget, 50% per-position cap, top relative opening volume, 10%-ATR stop, no leverage, and end-of-day exits. It is an implementation check, not a paper replication, because only ~60 sessions and three surviving symbols are available.

Total registered evaluations: **186**. This includes validation candidates, OOS screens, ablations, cost stresses, four selected-strategy folds, paper-mechanism runs, ORB runs, and cash/BTC/ETH/SPY/momentum/mean-reversion baselines. Compact parameters and metrics are in `research/profitability/summary.json`; the complete audit registry is `research/profitability/full_results.json.gz`, and raw selected forecasts are compressed CSVs.
