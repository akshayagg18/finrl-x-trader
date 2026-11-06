# ETF rotation challenger — staged result

**Outcome: historically stronger challenger; prospective paper comparison warranted**

The protocol was committed before the dedicated data snapshot was
downloaded. Development and validation selected and locked the winner
before the evaluation partition was opened.

Selected configuration: `mom252_sma200_top2_vol15` from 5 eligible configurations.

| Partition | Net return | Ending value | Maximum drawdown | Fills | Costs |
|---|---:|---:|---:|---:|---:|
| development | 7.17% | $535.83 | -6.51% | 68 | $4.97 |
| validation | 1.63% | $508.16 | -8.18% | 58 | $4.20 |
| evaluation | 22.55% | $612.75 | -4.60% | 74 | $4.47 |
| evaluation cost 2x | 21.57% | $607.87 | -4.68% | 74 | $8.90 |

## Evaluation benchmarks at the same $500 start

| Benchmark | Net return | Maximum drawdown |
|---|---:|---:|
| 40% SPY / 60% cash | 26.06% | -8.77% |
| 8% each ETF / 60% cash | 20.85% | -5.72% |

## Consistency diagnostics

- Independent two-month resets from January 2022: 17 profitable, 8 losing and 3 flat of 28.
- Average two-month return: 0.64% ($3.22).
- Average / worst two-month drawdown: -1.54% / -3.66%.
- Evaluation weeks: 86 profitable, 60 losing and 0 flat.
- Lower 95% weekly-mean bound: 0.065%.

## Decision boundary

Run this candidate only as a separate forward-paper challenger. Do not replace the frozen BTC/ETH account until both have comparable prospective evidence.

This is adjusted-price retrospective research with a current fixed
ETF universe, modeled proportional costs, fractional research units
and no taxes or cash yield. Yahoo history can be revised. It is not
a broker fill record and cannot alter the existing defensive forward
account. No external order was submitted.
