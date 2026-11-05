# BTC/ETH market-neutral relative-value research

The strategy trades deviations in the lagged log BTC/ETH price ratio. It holds equal-notional long and short legs, scales gross exposure by ratio volatility, and exits as the ratio approaches its rolling mean.

All periods were already inspected before this experiment. Results are
diagnostic and cannot establish an untouched out-of-sample edge.

## Chronological results

| Tier | Selected | Development | Validation | Evaluation | Stress | Drawdown | Long/cash comparator |
|---|---|---:|---:|---:|---:|---:|---:|
| drawdown 10 | `relative_value_60_2_0_weekly_vol_0.3` | 1.19% | 1.13% | -1.23% | -4.14% | -8.20% | 2.84% / -9.67% DD |
| drawdown 20 | `relative_value_60_2_0_weekly_vol_0.3` | 2.37% | 2.16% | -2.79% | -8.44% | -15.85% | 5.04% / -18.54% DD |
| drawdown 50 | `relative_value_60_2_0_weekly_vol_0.3` | 5.79% | 4.54% | -9.31% | -21.95% | -35.75% | 7.50% / -40.87% DD |

## Independent two-month windows

| Tier | Average P/L | Average return | Positive / negative / flat | Average drawdown | Worst drawdown |
|---|---:|---:|---:|---:|---:|
| drawdown 10 | $-1.29 | -0.26% | 4 / 15 / 10 | -0.64% | -2.21% |
| drawdown 20 | $-2.58 | -0.52% | 4 / 15 / 10 | -1.27% | -4.39% |
| drawdown 50 | $-6.47 | -1.29% | 4 / 15 / 10 | -3.14% | -10.74% |

## Qualification

### Drawdown 10

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **True**
- Complete evaluation weeks: 146; profitable 74, losing 72, flat 0
- Lower 95% weekly-mean bound: -0.08%
- Deployment qualified: **False**

### Drawdown 20

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **True**
- Complete evaluation weeks: 146; profitable 74, losing 72, flat 0
- Lower 95% weekly-mean bound: -0.17%
- Deployment qualified: **False**

### Drawdown 50

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **True**
- Complete evaluation weeks: 146; profitable 74, losing 72, flat 0
- Lower 95% weekly-mean bound: -0.42%
- Deployment qualified: **False**

## Material limitations

- Market neutrality removes first-order direction, not basis or spread risk.
- Both legs use spot prices as derivative proxies.
- Base short carry is charged at 10% annualized and stressed to 20%.
- Cointegration is not assumed to persist outside the measured history.
- A drawdown budget is an acceptance threshold, not a guaranteed loss cap.
- Fees, liquidity, eligibility and fills require target-account verification.
- No external order was submitted and no track is connected to broker routing.

Reproduce with `python -m scripts.evaluate_relative_value`.
