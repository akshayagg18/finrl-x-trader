"""Render the locked long-history regime experiment as a concise Markdown report."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("research/strategy_v2")


def _pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def main() -> None:
    protocol = json.loads((ROOT / "protocol.json").read_text())
    lock = json.loads((ROOT / "selection_locked.json").read_text())
    summary = json.loads((ROOT / "summary.json").read_text())
    rule = lock["rule"]
    model = lock["filter"]

    rows = []
    for name, result in summary.items():
        rows.append(
            "| "
            + " | ".join(
                [
                    name,
                    _pct(result["net_return"]),
                    _pct(result["same_trade_gross_return"]),
                    _pct(result["max_drawdown"]),
                    str(result["completed_trades"]),
                    "yes" if result["qualified"] else "no",
                ]
            )
            + " |"
        )

    base = summary["rule_base"]
    filtered = summary["ml_filter_base"]
    doubled = summary["ml_filter_cost_2x"]
    hold = summary["hold"]
    text = f"""# Locked long-history regime and ML experiment

## Decision

**No strategy qualified and nothing from this experiment is deployed.** The fixed
trend/momentum rule failed the untouched 2022 selection gate. Every tested ML
entry filter also lost money in that validation year. Live trading remains
disabled, and this research cannot enable it.

The diagnostic random-forest filter returned {_pct(filtered['net_return'])} from
2023 through October 2026 at modeled base costs, but this does not establish a
profitable model: its 2022 validation return was
{_pct(model['validation']['net_return'])}, doubled costs changed the later result
to {_pct(doubled['net_return'])}, the lower 95% weekly-mean bound was
{_pct(filtered['mean_weekly_return_lower_95'])}, and it completed only
{filtered['completed_trades']} exits. A 60%-deployed BTC/ETH hold benchmark
returned {_pct(hold['net_return'])} with a {_pct(hold['max_drawdown'])} maximum
drawdown; it is a benchmark, not an eligible trading policy.

## Frozen protocol

- Universe: BTC-USDT and ETH-USDT spot; $500 initial cash, 60% maximum deployed,
  30% per asset, 40% cash reserve.
- Data: Binance public hourly archives from August 2017 through October 2026.
  This is cross-venue research data and cannot verify OKX Singapore execution.
- Development: {protocol['development'][0]} through {protocol['development'][1]}.
- Selection/validation: {protocol['validation'][0]} through {protocol['validation'][1]}.
- Final untouched evaluation: {protocol['evaluation'][0]} through
  {protocol['evaluation'][1]}.
- Rule family: completed-daily trend, completed-four-hour momentum, and a
  rolling volatility regime; eight configurations were fixed in advance.
- ML filter: random forest or histogram gradient boosting, trained only on
  features and seven-day labels that matured before each cutoff. It can block
  entries but cannot postpone regime exits. Thresholds 0.55 and 0.60 were fixed.
- Costs: 10 bp fee plus 5 bp adverse execution per side, then 1.5x and 2x
  stresses. These are assumptions, not a verified account tariff.
- Risk: volatility-sized positions plus a 2% daily-loss pause, 8% portfolio
  drawdown halt, and regime-reset requirement after protective stops.

The selected diagnostic rule was `{rule['name']}`. Its development result was
{_pct(rule['development']['net_return'])}, followed by
{_pct(rule['validation']['net_return'])} in 2022, so it failed selection before
the evaluation period was opened. The rule subsequently returned
{_pct(base['net_return'])}; the drawdown halt stopped new exposure after the
loss threshold was crossed.

## Final evaluation

| Scenario | Net return | Same-trade gross | Max drawdown | Completed exits | Qualified |
|---|---:|---:|---:|---:|:---:|
{chr(10).join(rows)}

`same-trade gross` adds modeled fees and adverse execution back to the actual
filled quantities. It is cost attribution, not an executable zero-cost rerun.
The hold row buys both assets once at the configured 30% cap and does not use
the strategy's protective controls.

## Reproduce and inspect

```sh
python -m scripts.download_long_history
python -m scripts.evaluate_regime_strategy
python -m scripts.report_regime_strategy
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
"""
    (ROOT / "REPORT.md").write_text(text)
    print(ROOT / "REPORT.md")


if __name__ == "__main__":
    main()
