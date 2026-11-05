# Long/cash strategy with a BTC short hedge

The strategy keeps the existing weekly BTC-gated BTC/ETH long allocation in positive regimes. In negative regimes it may hold a BTC short sized to 25%, 50%, or 100% of the tier exposure limit.

All periods were already inspected before this experiment. Results are
diagnostic and cannot establish an untouched out-of-sample edge.

## Chronological results

| Tier | Selected | Development | Validation | Evaluation | Stress | Drawdown | Long/cash comparator |
|---|---|---:|---:|---:|---:|---:|---:|
| drawdown 10 | `short_hedge_trend_100_momentum_90_either_25` | 1.81% | 5.37% | -0.72% | -2.07% | -10.63% | 2.84% / -9.67% DD |
| drawdown 20 | `short_hedge_trend_100_momentum_90_either_25` | 3.44% | 10.68% | -2.18% | -4.83% | -20.29% | 5.04% / -18.54% DD |
| drawdown 50 | `short_hedge_trend_100_momentum_90_either_25` | 7.26% | 25.96% | -10.60% | -16.57% | -44.19% | 7.50% / -40.87% DD |

## Independent two-month windows

| Tier | Average P/L | Average return | Positive / negative / flat | Average drawdown | Worst drawdown |
|---|---:|---:|---:|---:|---:|
| drawdown 10 | $0.58 | 0.12% | 12 / 17 / 0 | -1.78% | -6.32% |
| drawdown 20 | $1.25 | 0.25% | 12 / 17 / 0 | -3.52% | -12.40% |
| drawdown 50 | $3.78 | 0.76% | 12 / 17 / 0 | -8.57% | -29.31% |

## Qualification

### Drawdown 10

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **False**
- Complete evaluation weeks: 146; profitable 71, losing 75, flat 0
- Lower 95% weekly-mean bound: -0.14%
- Deployment qualified: **False**

### Drawdown 20

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **False**
- Complete evaluation weeks: 146; profitable 71, losing 75, flat 0
- Lower 95% weekly-mean bound: -0.27%
- Deployment qualified: **False**

### Drawdown 50

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **True**
- Complete evaluation weeks: 146; profitable 71, losing 75, flat 0
- Lower 95% weekly-mean bound: -0.67%
- Deployment qualified: **False**

## Material limitations

- The short is modeled from spot prices; no futures order book is available.
- Base short carry is charged at 10% annualized and stressed to 20%.
- Liquidation, margin calls, funding sign changes and basis are not observed.
- A drawdown budget is an acceptance threshold, not a guaranteed loss cap.
- Fees, liquidity, eligibility and fills require target-account verification.
- No external order was submitted and no track is connected to broker routing.

Reproduce with `python -m scripts.evaluate_short_hedge`.
