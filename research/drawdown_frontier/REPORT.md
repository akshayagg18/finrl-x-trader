# Drawdown frontier: 20% and 50% budgets

This diagnostic scales the defensive trend family to higher exposure.
A drawdown budget is an acceptance threshold, not a stop-loss guarantee.
Price gaps, liquidity and execution failures can produce larger losses.
The history was already inspected, so these results are not a fresh
holdout and cannot qualify either tier for deployment.

## Results

| Tier | Maximum exposure | Development | Validation | Evaluation | 2x cost | Evaluation drawdown | Passive return / drawdown |
|---|---:|---:|---:|---:|---:|---:|---:|
| drawdown 20 | 40% | 14.34% | 9.45% | 5.04% | 3.97% | -18.54% | 16.41% / -36.58% |
| drawdown 50 | 100% | 38.79% | 23.41% | 7.50% | 4.79% | -40.87% | 41.02% / -58.53% |

## Independent two-month windows

| Tier | Average P/L | Average return | Positive / negative / flat | Average drawdown | Worst drawdown |
|---|---:|---:|---:|---:|---:|
| drawdown 20 | $2.04 | 0.41% | 10 / 9 / 10 | -2.44% | -11.95% |
| drawdown 50 | $5.72 | 1.14% | 10 / 9 / 10 | -5.93% | -28.39% |

## Interpretation

Among the newly requested tiers, the 20% budget has the stronger
return-to-drawdown tradeoff. Moving to the 50% budget added only
2.46% of evaluation return while
worsening measured drawdown by 22.33%.
The 50% tier is not preferred.
The earlier 10% tier remains the least damaging measured option.

Exposure scaling increases both modeled profit and loss. The passive
comparators use the same maximum allocation, while the trend strategy
often holds less because of volatility scaling or remains fully in cash.
Cash earns 0% in every scenario.

### Drawdown 20

- Selected configuration: `trend_100_momentum_90_weekly_btc_gate`
- Realized evaluation drawdown within budget: **True**
- Complete weeks: 146; profitable: 44; losing: 39; flat: 63
- Lower 95% weekly-mean bound: -0.21%

### Drawdown 50

- Selected configuration: `trend_100_momentum_90_weekly_btc_gate`
- Realized evaluation drawdown within budget: **True**
- Complete weeks: 146; profitable: 44; losing: 39; flat: 63
- Lower 95% weekly-mean bound: -0.51%

No tier is promoted. Both require a new prospective paper period,
verified target-venue costs and account isolation. The 50% budget can
lose roughly half the $500 account in the modeled path and can lose
more in real execution. No external order was sent.

Reproduce with `python -m scripts.evaluate_drawdown_frontier`.
