# Long/cash strategy with synthetic protective puts

The existing weekly BTC-gated long allocation buys rolling BTC and ETH puts covering 50% or 100% of exposure. Puts are marked with Black-Scholes using lagged 30-day realized volatility plus a 25% markup.

All periods were already inspected before this experiment. Results are
diagnostic and cannot establish an untouched out-of-sample edge.

## Chronological results

| Tier | Selected | Development | Validation | Evaluation | Stress | Drawdown | Long/cash comparator |
|---|---|---:|---:|---:|---:|---:|---:|
| drawdown 10 | `put_trend_100_momentum_90_otm_15_coverage_50_tenor_28` | 6.49% | 4.05% | 1.94% | 0.28% | -9.50% | 2.84% / -9.67% DD |
| drawdown 20 | `put_trend_100_momentum_90_otm_15_coverage_50_tenor_28` | 13.31% | 8.05% | 3.28% | -0.02% | -18.22% | 5.04% / -18.54% DD |
| drawdown 50 | `put_trend_100_momentum_90_otm_15_coverage_50_tenor_28` | 35.77% | 19.63% | 3.58% | -4.34% | -40.18% | 7.50% / -40.87% DD |

## Independent two-month windows

| Tier | Average P/L | Average return | Positive / negative / flat | Average drawdown | Worst drawdown |
|---|---:|---:|---:|---:|---:|
| drawdown 10 | $0.74 | 0.15% | 10 / 9 / 10 | -1.17% | -5.48% |
| drawdown 20 | $1.56 | 0.31% | 10 / 9 / 10 | -2.31% | -10.79% |
| drawdown 50 | $4.45 | 0.89% | 10 / 9 / 10 | -5.64% | -25.70% |

## Qualification

### Drawdown 10

- Passed development/validation selection: **True**
- Historically profitable condition: **True**
- Within drawdown budget: **True**
- Complete evaluation weeks: 146; profitable 38, losing 45, flat 63
- Lower 95% weekly-mean bound: -0.10%
- Deployment qualified: **False**

### Drawdown 20

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **True**
- Complete evaluation weeks: 146; profitable 38, losing 45, flat 63
- Lower 95% weekly-mean bound: -0.20%
- Deployment qualified: **False**

### Drawdown 50

- Passed development/validation selection: **True**
- Historically profitable condition: **False**
- Within drawdown budget: **True**
- Complete evaluation weeks: 146; profitable 38, losing 45, flat 63
- Lower 95% weekly-mean bound: -0.51%
- Deployment qualified: **False**

## Material limitations

- No historical option-chain quotes or volatility surface are available.
- Black-Scholes marks omit skew, jumps, exchange margin and quote depth.
- Stress doubles trading friction and raises modeled implied volatility 25%.
- These are synthetic insurance estimates, not executable option backtests.
- A drawdown budget is an acceptance threshold, not a guaranteed loss cap.
- Fees, liquidity, eligibility and fills require target-account verification.
- No external order was submitted and no track is connected to broker routing.

Reproduce with `python -m scripts.evaluate_put_protection`.
