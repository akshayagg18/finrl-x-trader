# Cost-aware Bitcoin paper replication

## Source examined

[Bysik & Ślepaczuk (2026), *Machine Learning-Based Bitcoin Trading Under Transaction Costs: Evidence From Walk-Forward Forecasting*](https://arxiv.org/abs/2606.00060), including the full methodology and appendices.

The paper uses Binance BTC-USDT USD-margined futures hourly OHLCV from December 2017 to January 2026, a 12-month train / 3-month validation / 3-month test rolling design with 27 test folds, and next-hour log-return prediction. Its cost-aware rule changes position only when:

`abs(prediction) > lambda * cost_per_position_change * abs(target_position - current_position)`

The headline configuration uses `lambda=2` and 10 bps per position change, making a long-only entry/exit hurdle 20 bps. The paper reports strong aggregate XGBoost performance, but also a roughly 76.6% maximum drawdown, many low-trade folds, and only 16 profitable folds out of 27. The authors do not establish statistically robust XGBoost dominance over the neural models.

## What was reproduced

- Hourly OHLCV expected-return regression with XGBoost.
- Published XGBoost search-space-compatible parameters: depth 3, learning rate 0.02, 1,000 estimators for the mechanism run, min-child weight 20, 75% row/column sampling, L1/L2 regularization.
- Long-only cash state.
- `lambda=2` position-change filter.
- Chronological fitting with label maturity before cutoff.
- Causal technical features and raw forecast logging.
- Next-open fills, explicit costs, $500 capital, 60% maximum exposure, no leverage.

## Material differences

This is a **mechanism replication and spot adaptation**, not a reproduction of the paper's reported return:

| Paper | Repository experiment |
|---|---|
| Binance USD-margined futures | OKX BTC-USDT spot |
| 2017-12 to 2026-01 | 2024-11 to 2026-10 |
| 27 folds, 12/3/3 months | Four selected-strategy folds, 9/3/3 months |
| Full binary position; futures | 60% cash-account exposure; no borrowing |
| 10 bps per position change | 15 bps estimated per side |
| Decision applied to next close-to-close return | Completed-bar signal, next-open execution |
| EGARCH feature tier evaluated | Interpretable OHLCV/TA features; no EGARCH |

## Measured result

Development OOS, 2025-11-01 through 2026-08-01:

| Metric | Local paper-style mechanism |
|---|---:|
| Starting / ending equity | $500.00 / $472.27 |
| Net return | -5.55% |
| Maximum drawdown | -8.22% |
| Sharpe / Sortino | -1.16 / -1.25 |
| Completed trades | 4 |
| Win rate / profit factor | 50.0% / 0.25 |
| Average net P&L per trade | -$6.93 |
| Total modeled costs | $3.56 |
| Time invested | 3.19% |
| Portfolio halt | Triggered |

The model emitted 3,587 positive gross candidates and 71 net-threshold candidates. It submitted eight fills (four round trips); 67 later candidates were blocked after the drawdown halt.

At 1.5x and 2x costs, the endogenous hurdle selected a different two-trade subset and returned +1.93% and +1.32%. These are **not robustness evidence**: the base strategy was negative, the trade sets changed, and two trades are statistically meaningless.

## Interpretation

The paper's conversion rule is important and correctly reduces turnover, but its published profitability did not transfer to the shorter spot sample under the $500 risk limits. The local result supports the paper's warning about regime dependence, not its headline return. No paper return is claimed as reproduced.
