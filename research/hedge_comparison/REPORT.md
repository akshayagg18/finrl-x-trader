# Four-track hedge comparison

## Decision

**The existing long/cash trend strategy remains the best historical
candidate at every risk tier. No track is qualified for deployment.**
The BTC short hedge and BTC/ETH relative-value tracks failed the later
evaluation. Protective puts slightly reduced drawdown but surrendered
more return than they protected and failed stress above the 10% tier.

## Evaluation comparison: January 2024 through October 2026

| Track | Tier | Net return | Stress return | Max drawdown | Avg two-month return | Positive / negative / flat windows | Weekly lower 95% |
|---|---|---:|---:|---:|---:|---:|---:|
| long cash | drawdown 10 | 2.84% | 2.31% | -9.67% | 0.20% | 10 / 9 / 10 | -0.10% |
| long cash | drawdown 20 | 5.04% | 3.97% | -18.54% | 0.41% | 10 / 9 / 10 | -0.21% |
| long cash | drawdown 50 | 7.50% | 4.79% | -40.87% | 1.14% | 10 / 9 / 10 | -0.51% |
| short hedge | drawdown 10 | -0.72% | -2.07% | -10.63% | 0.12% | 12 / 17 / 0 | -0.14% |
| short hedge | drawdown 20 | -2.18% | -4.83% | -20.29% | 0.25% | 12 / 17 / 0 | -0.27% |
| short hedge | drawdown 50 | -10.60% | -16.57% | -44.19% | 0.76% | 12 / 17 / 0 | -0.67% |
| relative value | drawdown 10 | -1.23% | -4.14% | -8.20% | -0.26% | 4 / 15 / 10 | -0.08% |
| relative value | drawdown 20 | -2.79% | -8.44% | -15.85% | -0.52% | 4 / 15 / 10 | -0.17% |
| relative value | drawdown 50 | -9.31% | -21.95% | -35.75% | -1.29% | 4 / 15 / 10 | -0.42% |
| put protection | drawdown 10 | 1.94% | 0.28% | -9.50% | 0.15% | 10 / 9 / 10 | -0.10% |
| put protection | drawdown 20 | 3.28% | -0.02% | -18.22% | 0.31% | 10 / 9 / 10 | -0.20% |
| put protection | drawdown 50 | 3.58% | -4.34% | -40.18% | 0.89% | 10 / 9 / 10 | -0.51% |

## What each track established

1. **Long/cash:** positive in all chronological partitions and cost
   stress, but modest later returns and negative weekly confidence bounds.
2. **BTC short hedge:** selected on development/validation, then lost
   money at every evaluation tier. Short rebounds and carry erased gains.
3. **Market-neutral relative value:** later ratio behavior did not
   mean-revert reliably enough to overcome turnover and short carry.
4. **Protective puts:** the 10% tier stayed positive under synthetic
   stress, but underperformed unhedged long/cash for only a small
   drawdown improvement. Higher tiers lost money under stress.

## Boundaries

The short and pair tracks use spot prices as derivative proxies and
charge explicit carry. The put track uses Black-Scholes marks from lagged
realized volatility because historical option chains are unavailable.
These assumptions are useful rejection tests, not executable fills.
All history is now inspected. The only valid next profitability test is
a frozen prospective paper observation; increasing leverage cannot turn
these retrospective results into a reliable profit promise.

No real, paper-broker, short, derivative, or option order was submitted.
