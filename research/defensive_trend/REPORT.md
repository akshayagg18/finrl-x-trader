# Defensive BTC/ETH trend research

## Result

This search found a **historically profitable candidate**, but it is
**not qualified for broker deployment**. It made money after modeled
costs in all three chronological partitions and at doubled costs in the
last partition. That is retrospective evidence, not a promise of future
profit or consistent weekly income.

The selected rule checks every Monday at 00:00 UTC. It uses only the
previous completed close: BTC must be above its 100-day
average and have positive 90-day momentum. When
the gate is open, BTC and ETH may each receive up to 10% of equity,
scaled down when 30-day annualized volatility exceeds 30%. At least 80%
remains cash. The gate closing returns the allocation to cash.

## Chronological results

| Partition | Dates | Net return | Ending value | Max drawdown | Fills |
|---|---|---:|---:|---:|---:|
| development | 2019-01-01 to 2021-12-31 | 6.98% | $534.91 | -1.23% | 20 |
| validation | 2022-01-01 to 2023-12-31 | 4.73% | $523.63 | -3.28% | 62 |
| evaluation | 2024-01-01 to 2026-10-31 | 2.84% | $514.18 | -9.67% | 170 |
| evaluation cost 2x | 2024-01-01 to 2026-10-31 | 2.31% | $511.55 | -9.86% | 170 |

The same-risk passive comparator (10% BTC, 10% ETH, 80% cash) returned
**8.20%** with **-22.51%**
maximum drawdown during the evaluation partition. Cash earns 0% in
both simulations, so neither result includes interest on the reserve.

## Independent two-month windows

From January 2022 through October 2026, 29 reset
windows averaged **$0.98**
(**0.20%**) with **-1.23%**
average maximum drawdown. 10 gained,
9 lost, and 10 were flat.
These arithmetic window averages are not a compounded account return.

| Window | P/L | Return | Maximum drawdown |
|---|---:|---:|---:|
| 2022-01 to 2022-02 | $0.00 | 0.00% | 0.00% |
| 2022-03 to 2022-04 | $-3.96 | -0.79% | -0.81% |
| 2022-05 to 2022-06 | $0.00 | 0.00% | 0.00% |
| 2022-07 to 2022-08 | $0.00 | 0.00% | 0.00% |
| 2022-09 to 2022-10 | $0.00 | 0.00% | 0.00% |
| 2022-11 to 2022-12 | $0.00 | 0.00% | 0.00% |
| 2023-01 to 2023-02 | $6.41 | 1.28% | -1.06% |
| 2023-03 to 2023-04 | $9.51 | 1.90% | -1.10% |
| 2023-05 to 2023-06 | $0.00 | 0.00% | 0.00% |
| 2023-07 to 2023-08 | $-13.34 | -2.67% | -3.28% |
| 2023-09 to 2023-10 | $11.27 | 2.25% | -0.23% |
| 2023-11 to 2023-12 | $13.16 | 2.63% | -0.83% |
| 2024-01 to 2024-02 | $30.90 | 6.18% | -1.84% |
| 2024-03 to 2024-04 | $-2.31 | -0.46% | -2.39% |
| 2024-05 to 2024-06 | $4.83 | 0.97% | -0.63% |
| 2024-07 to 2024-08 | $-11.82 | -2.36% | -2.36% |
| 2024-09 to 2024-10 | $-4.00 | -0.80% | -1.85% |
| 2024-11 to 2024-12 | $21.85 | 4.37% | -1.55% |
| 2025-01 to 2025-02 | $-8.09 | -1.62% | -2.05% |
| 2025-03 to 2025-04 | $0.00 | 0.00% | 0.00% |
| 2025-05 to 2025-06 | $1.66 | 0.33% | -1.93% |
| 2025-07 to 2025-08 | $15.35 | 3.07% | -1.60% |
| 2025-09 to 2025-10 | $-10.34 | -2.07% | -3.04% |
| 2025-11 to 2025-12 | $0.00 | 0.00% | 0.00% |
| 2026-01 to 2026-02 | $0.00 | 0.00% | 0.00% |
| 2026-03 to 2026-04 | $0.00 | 0.00% | 0.00% |
| 2026-05 to 2026-06 | $-25.95 | -5.19% | -6.08% |
| 2026-07 to 2026-08 | $0.35 | 0.07% | -0.38% |
| 2026-09 to 2026-10 | $-7.16 | -1.43% | -2.60% |

## Selection and limits

The search evaluated **81** prespecified combinations;
**14** passed development and
validation gates. Selection ranked only validation return among those
eligible candidates. The final period was already viewed during
exploratory work before this formal record, so it is chronological but
not a pristine holdout. Multiple testing can exaggerate apparent edge.

Historical profitability condition: **True**.
Deployment qualified: **False**.

Deployment remains blocked because:

- The final historical interval was inspected during exploratory tuning.
- No new 12-week prospective paper observation has completed.
- Target-account fees, liquidity, eligibility, and actual fills are unverified.
- Insufficient completed trades
- Positive lower 95% block-bootstrap bound not established

Data are public Binance spot hourly archives. Fees, adverse fills,
market depth, USDT/USD parity, target-broker eligibility, taxes, and
cash yield are not verified. No real or broker-paper order was sent.
A new prospective paper period is required before deployment is
reconsidered.

Reproduce with `python -m scripts.evaluate_defensive_trend`.
