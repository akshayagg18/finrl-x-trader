# Profitability research results

## Result

**NO QUALIFIED PROFITABLE STRATEGY FOUND.**

No ML configuration had positive net performance with an adequate trade sample and cost robustness. The frozen hourly candidate generated zero final-holdout trades. The simple momentum comparator was positive in that three-month period but lagged passive BTC exposure and nearly exhausted the 8% drawdown budget.

## Ranked out-of-sample evidence

Periods differ and are shown explicitly; they must not be compounded or treated as one account.

| Rank | Strategy | Period / status | Net P&L | Net return | Max DD | Trades | Higher-cost result | Benchmark comparison |
|---:|---|---|---:|---:|---:|---:|---|---|
| 1 | 60% BTC buy-and-hold | 2026-08 to Oct, final comparator | +$68.73 | +13.75% | -8.18% | 1 | Not stressed; passive comparator | Best final-period return; no active risk halt |
| 2 | 60% ETH buy-and-hold | 2026-08 to Oct, final comparator | +$62.11 | +12.42% | -14.60% | 1 | Not stressed; passive comparator | High return with materially larger drawdown |
| 3 | Simple BTC 24h momentum | 2026-08 to Oct, final comparator | +$13.17 | +2.63% | -8.19% | 29 | Not a selected candidate | Underperformed BTC hold by 11.11 percentage points |
| 4 | Frozen hourly XGBoost | 2026-08 to Oct, final strategy holdout | $0.00 | 0.00% | 0.00% | 0 | 0% at 1.5x / 2x; still cash | Tied cash; underperformed both passive comparators and momentum |
| 5 | Cash | Same final period | $0.00 | 0.00% | 0.00% | 0 | N/A | No active edge |
| 6 | Long-only 15m equity ORB pilot | ~60 sessions, limited pilot | -$5.91 | -1.18% | -1.18% | 25 | -1.44% / -1.72% | Lost money, though SPY also declined in this narrow sample |
| 7 | 60% SPY buy-and-hold | Same limited equity sample | -$8.14 | -1.63% | -2.30% | 1 | Not stressed; passive comparator | ORB lost less, but neither was profitable |
| 8 | Simple BTC 24h mean reversion | 2026-08 to Oct, final comparator | -$24.13 | -4.83% | -6.50% | 65 | Not a selected candidate | 56.9% wins did not overcome poor payoff ratio and $57.68 costs |
| 9 | Paper-style hourly XGBoost mechanism | 2025-11 to 2026-07 development OOS | -$27.73 | -5.55% | -8.22% | 4 | +1.93% / +1.32% on different two-trade subsets | Failed base case and sample gate |

## Final selected-strategy metrics

| Metric | Value |
|---|---:|
| Starting / ending capital | $500 / $500 |
| Net return / profit | 0.00% / $0.00 |
| Annualized return | 0.00% (cash result, not a strategy edge) |
| Maximum drawdown | 0.00% |
| Sharpe / Sortino | Undefined; no variable returns |
| Trades / fills | 0 / 0 |
| Fees / slippage | $0 / $0 |
| Turnover / time invested | 0 / 0% |
| Win rate / profit factor | Undefined |
| BTC 60% buy-and-hold | +13.75% |
| ETH 60% buy-and-hold | +12.42% |
| Simple momentum | +2.63% |
| Simple mean reversion | -4.83% |

Forecast diagnostics explain the zero trades: 49.73% direction accuracy, -0.0164 Spearman correlation, 0.2035% maximum prediction, and 0.4827% frozen entry hurdle. None of 900 positive forecasts survived cost plus calibrated uncertainty. No risk or order-size rule rejected a candidate.

## Equity ORB pilot

| Metric | Value |
|---|---:|
| Net return | -1.18% |
| Maximum drawdown | -1.18% |
| Trades | 25 |
| Win rate | 8.0% |
| Profit factor | 0.46 |
| Average P&L / trade | -$0.24 |
| Modeled costs | $3.33 |
| 1.5x / 2x cost returns | -1.44% / -1.72% |

This result cannot refute or confirm the published Stocks-in-Play paper. The local data lacks its 5-minute bars, 7,000-stock survivorship-free universe, long-short legs, and $25,000/4x sizing.

The passive SPY comparator lost 1.63% in the same limited sample. ORB therefore beat SPY by about 0.45 percentage points but still lost money and does not satisfy the absolute-profitability gate.

## Artifacts

- `research/profitability/summary.json`: compact registry and metrics for the dashboard.
- `research/profitability/full_results.json.gz`: complete audit registry including per-bar equity points.
- `research/profitability/selection_locked.json`: selection frozen before final fold.
- `research/profitability/selected_fold_*_forecasts.csv.gz`: raw forecasts, hurdles, regimes, actions, and rejection reasons.
- `research/profitability/paper_mechanism_forecasts.csv.gz`: paper-rule diagnostics.
- `research/profitability/orb_signal_diagnostics.csv`: equity eligibility diagnostics.
- `research/profitability/selected_equity_drawdown.png`: final equity/drawdown chart.

All results are historical simulations with estimated costs. None are brokerage paper fills or real-money returns.

## Verification

- Focused profitability tests: 6 passed.
- Compatible non-native regression subset: 42 passed.
- JavaScript syntax, Python bytecode compilation, and whitespace checks passed.
- The full suite was attempted but could not collect five Nautilus/API/UI modules because Windows Application Control blocked the installed `pyarrow.lib` native extension. This is an environment policy failure, not a passing full-suite claim; the previous repository verification remains 67 passed in `research/growth/verification_tests.txt`.
