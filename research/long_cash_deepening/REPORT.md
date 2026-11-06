# Long/cash deepening — results

Both tracks remain long-only with a cash fallback. Historical partitions
were already inspected, so these are diagnostic improvements rather than
fresh holdouts.

## Crypto long/cash

Selected `majority_btc_gate_weekly_vol40` from 33 eligible configurations.

| Scenario | Return | Drawdown | Ending value |
|---|---:|---:|---:|
| evaluation | 27.40% | -12.39% | $637.00 |
| cost 2x | 26.08% | -12.65% | $630.41 |
| cost 4x | 23.48% | -13.16% | $617.41 |
| delay 1 day | 20.14% | -12.80% | $600.71 |
| frozen comparison | 5.04% | -18.54% | $525.19 |

Two-month resets: 11 profitable, 8 losing, 10 flat; average 1.26% ($6.29).
Calendar-year resets: {'2024': 0.22252555665873874, '2025': 0.083785276546821, '2026': -0.057880930232425576}.
Lower 95% weekly-mean bound: -0.104%.
Decision: **separate prospective challenger warranted**.

## ETF long/cash

Selected `asset20_deploy40_vol20` from 14 eligible configurations.

| Scenario | Return | Drawdown | Ending value |
|---|---:|---:|---:|
| evaluation | 25.20% | -5.35% | $626.01 |
| cost 2x | 24.20% | -5.43% | $621.00 |
| cost 4x | 22.21% | -5.59% | $611.03 |
| delay 1 session | 24.20% | -5.01% | $620.99 |
| delay 3 sessions | 23.23% | -5.03% | $616.16 |
| minimum order 10 | 25.70% | -5.36% | $628.51 |
| frozen comparison | 22.55% | -4.60% | $612.75 |

Two-month resets: 17 profitable, 8 losing, 3 flat; average 0.69% ($3.46).
The 40%-SPY/cash comparison returned 26.06% with -8.77% drawdown.
Calendar-year resets: {'2024': 0.07554601247769677, '2025': 0.12109786849945259, '2026': 0.03189155957342793}.
Lower 95% weekly-mean bound: 0.071%.
All single-asset removal tests remained profitable: **True**.
Decision: **separate prospective challenger warranted**.

## Boundary

Higher exposure is not a new source of alpha. Results must be read with
their drawdown, passive SPY/cash comparison, cost and delay stresses.
Neither result changes the running forward account or authorizes broker
orders. A historically stronger extension requires a separate prospective
record before any deployment decision.
