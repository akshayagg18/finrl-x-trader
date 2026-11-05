# Locked long-history regime and ML experiment

## Decision

**No strategy qualified and nothing from this experiment is deployed.** The fixed
trend/momentum rule failed the untouched 2022 selection gate. Every tested ML
entry filter also lost money in that validation year. Live trading remains
disabled, and this research cannot enable it.

The diagnostic random-forest filter returned -1.77% from
2023 through October 2026 at modeled base costs, but this does not establish a
profitable model: its 2022 validation return was
-1.35%, doubled costs changed the later result
to -6.08%, the lower 95% weekly-mean bound was
-0.06%, and it completed only
197 exits. A 60%-deployed BTC/ETH hold benchmark
returned 136.93% with a -52.35% maximum
drawdown; it is a benchmark, not an eligible trading policy.

## Frozen protocol

- Universe: BTC-USDT and ETH-USDT spot; $500 initial cash, 60% maximum deployed,
  30% per asset, 40% cash reserve.
- Data: Binance public hourly archives from August 2017 through October 2026.
  This is cross-venue research data and cannot verify OKX Singapore execution.
- Development: 2019-01-01 through 2021-12-31 23:00:00+00:00.
- Selection/validation: 2022-01-01 through 2022-12-31 23:00:00+00:00.
- Final untouched evaluation: 2023-01-01 through
  2026-10-31 23:00:00+00:00.
- Rule family: completed-daily trend, completed-four-hour momentum, and a
  rolling volatility regime; eight configurations were fixed in advance.
- ML filter: random forest or histogram gradient boosting, trained only on
  features and seven-day labels that matured before each cutoff. It can block
  entries but cannot postpone regime exits. Thresholds 0.55 and 0.60 were fixed.
- Costs: 10 bp fee plus 5 bp adverse execution per side, then 1.5x and 2x
  stresses. These are assumptions, not a verified account tariff.
- Risk: volatility-sized positions plus a 2% daily-loss pause, 8% portfolio
  drawdown halt, and regime-reset requirement after protective stops.

The selected diagnostic rule was `trend_20_100_mom_24_q80`. Its development result was
11.27%, followed by
-1.65% in 2022, so it failed selection before
the evaluation period was opened. The rule subsequently returned
-6.45%; the drawdown halt stopped new exposure after the
loss threshold was crossed.

## Final evaluation

| Scenario | Net return | Same-trade gross | Max drawdown | Completed exits | Qualified |
|---|---:|---:|---:|---:|:---:|
| rule_base | -6.45% | -3.44% | -8.12% | 109 | no |
| rule_cost_1.5x | -6.47% | -2.35% | -8.04% | 102 | no |
| rule_cost_2x | -6.56% | -2.79% | -8.04% | 69 | no |
| ml_filter_base | -1.77% | 5.08% | -7.08% | 197 | no |
| ml_filter_cost_1.5x | -6.07% | 1.75% | -8.06% | 151 | no |
| ml_filter_cost_2x | -6.08% | -2.71% | -8.02% | 55 | no |
| cash | 0.00% | 0.00% | 0.00% | 0 | no |
| hold | 136.93% | 137.12% | -52.35% | 0 | no |

`same-trade gross` adds modeled fees and adverse execution back to the actual
filled quantities. It is cost attribution, not an executable zero-cost rerun.
The hold row buys both assets once at the configured 30% cap and does not use
the strategy's protective controls.

The separate [two-month hold analysis](HOLD_2MONTH_REPORT.md) resets the same
$500 allocation for every non-overlapping two-month window from January 2022
through October 2026 and reports every window's P/L and drawdown.

## Reproduce and inspect

```sh
python -m scripts.download_long_history
python -m scripts.evaluate_regime_strategy
python -m scripts.report_regime_strategy
python -m scripts.evaluate_hold_windows
```

The downloader records every archive URL and SHA-256 in `data/*.json` and keeps
missing vendor hours explicit. `protocol.json` and `selection_locked.json`
record the pre-evaluation rules and selected diagnostic candidates. Trial-level
selection results are in `rule_trials.json` and `filter_trials.json`; compressed
fills/equity, weekly returns, model manifests, and cost attribution are retained
beside this report. Runtime model binaries are reproducible and excluded from
Git.

The next valid research iteration must define a materially different hypothesis
and lock it before using a new held-out period. Repeatedly tuning this family on
2023–2026 would turn the final evaluation into training data. A candidate must
pass both retrospective gates and a real 12-week forward paper observation
before broker paper deployment is considered.
