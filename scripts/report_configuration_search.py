"""Build an offline chart, CSV comparisons and a report from saved real backtests."""

import hashlib
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from trader.metrics import metrics

ROOT = Path("research/configuration_search_2026-11-03")


def main():
    result = json.loads((ROOT / "summary.json").read_text())
    winner = result["selection"]["selected"]
    chosen = json.loads((ROOT / f"test_fresh_{winner}_detail.json").read_text())
    baseline = json.loads((ROOT / "test_fresh_baseline_detail.json").read_text())
    curves = {
        "Selected Adaptive Rotation": [p["equity"] for p in chosen["equity"]],
        "Existing defaults": [p["equity"] for p in baseline["equity"]],
        "SPY buy and hold": [p["SPY"] for p in chosen["equity"]],
        "QQQ buy and hold": [p["QQQ"] for p in chosen["equity"]],
    }
    dates = [p["date"] for p in chosen["equity"]]
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        subplot_titles=["Portfolio value ($500 initial)", "Drawdown from peak"],
        vertical_spacing=0.12,
    )
    rows = []
    for name, values in curves.items():
        series = pd.Series([500.0, *values])
        drawdown = (series / series.cummax() - 1).iloc[1:]
        fig.add_trace(go.Scatter(x=dates, y=values, name=name), row=1, col=1)
        fig.add_trace(
            go.Scatter(x=dates, y=drawdown, name=name, showlegend=False), row=2, col=1
        )
        m = metrics([{"date": d, "equity": v} for d, v in zip(dates, values)], [], 500)
        rows.append(
            {
                "configuration": name,
                "ending_equity": values[-1],
                "return": m["total_return"],
                "max_drawdown": m["max_drawdown"],
                "annualized_return": m["annualized_return"],
                "sharpe": m["sharpe"],
            }
        )
    fig.update_layout(
        template="plotly_white",
        height=800,
        hovermode="x unified",
        title="Untouched test: 2025-10-08 to 2026-10-30 · simulated historical results",
        legend={"orientation": "h", "y": -0.12},
        margin={"b": 120},
    )
    fig.update_yaxes(tickprefix="$", row=1, col=1)
    fig.update_yaxes(tickformat=".1%", row=2, col=1)
    html = fig.to_html(include_plotlyjs=True, div_id="configuration-comparison")
    (ROOT / "comparison.html").write_text(
        "\n".join(line.rstrip() for line in html.splitlines()) + "\n"
    )
    pd.DataFrame(rows).to_csv(ROOT / "final_comparison.csv", index=False)
    pd.DataFrame({"date": dates, **curves}).to_csv(
        ROOT / "final_equity.csv", index=False
    )
    pd.DataFrame(chosen["orders"]).to_csv(ROOT / "selected_trades.csv", index=False)

    table = "\n".join(
        f"| {r['configuration']} | ${r['ending_equity']:.2f} | {r['return']:+.2%} | {r['max_drawdown']:.2%} |"
        for r in rows
    )
    stress = "\n".join(
        f"| {label} | ${r['ending_equity']:.2f} | {r['total_return']:+.2%} | {r['max_drawdown']:.2%} | {r['orders']} |"
        for label, r in zip(
            [
                "20 bps slippage + 10 bps full spread",
                "$1 per order + base spread/slippage",
            ],
            result["stress"],
        )
    )
    periods = []
    for label, period in [
        ("train0", "2022 training"),
        ("train1", "2023 training"),
        ("validation", "2024 validation"),
        ("test_previous", "2025 Jan 2–Oct 7 (previously inspected baseline)"),
    ]:
        r = json.loads((ROOT / f"{label}_{winner}.json").read_text())
        periods.append(
            f"| {period} | {r['total_return']:+.2%} | {r['max_drawdown']:.2%} | {r['SPY_return']:+.2%} | {r['QQQ_return']:+.2%} |"
        )
    period_table = "\n".join(periods)
    report = f"""# Configuration experiment: completed 2026-11-03 (Singapore)

**No configuration demonstrated a reliable profit advantage. Do not promote the selected candidate to live trading on this evidence.** Across 61 configurations and 136 historical simulations, the training/validation-selected candidate lost **2.82%** on the untouched final period. Existing defaults and both benchmarks performed better. Deployment settings were not changed; no broker orders were submitted.

## Untouched final test

2025-10-08 through 2026-10-30; each simulation starts with $500 and no holdings.

| Configuration | Ending value | Net return | Maximum drawdown |
|---|---:|---:|---:|
{table}

[Open the interactive chart offline](comparison.html). Download the file and open it in a browser; GitHub does not render interactive HTML. Chart dependencies are embedded. Daily values are in [final_equity.csv](final_equity.csv); all selected simulated fills are in [selected_trades.csv](selected_trades.csv).

The candidate executed 41 orders versus 151 for the defaults. Both remained below their configured portfolio halt thresholds. SPY/QQQ benchmarks are fully invested, include the same entry friction, and have no ongoing rebalancing. The strategy can hold substantial cash: its 80% deployment setting is a ceiling, not a target or a guarantee of 80% exposure. No interest is credited to cash. Returns are after modeled costs, before taxes, and based on closing mark-to-market values without a forced final liquidation.

## Selection procedure fixed before the final test

1. Fix the same 12-stock universe for every configuration: AAPL, MSFT, NVDA, AMZN, JPM, GS, XOM, CVX, JNJ, PG, KO, NEE.
2. Evaluate the default configuration, 48 Adaptive Rotation variants and 12 upstream Equal Weight variants on two independent training folds: 2022-01-03–2022-12-30 and 2023-01-03–2023-12-29. The grid varies deployment (60/80/95%), volatility target (30/45/60% linked to deployment), weekly/monthly cadence, 8/15% position stops, optional 15% trailing stops, and one/two stocks per rotation group.
3. Rank by compounded training-fold return, requiring observed drawdown no worse than 20% in both folds. The compounded score is a ranking statistic; folds reset state and are **not** a continuous multi-year account.
4. Advance the top eight eligible candidates, including the baseline (already among the eight), to 2024-01-02–2024-12-31. Choose maximum validation net return, again requiring observed drawdown no worse than 20%.
5. Save [selection_locked.json](selection_locked.json) before evaluating either test interval. Fetch newer Yahoo data only after selecting the candidate. Evaluate the selected candidate and baseline, without retuning, on the final period.

All 136 simulations completed without errors: 122 training, 8 validation, 4 test and 2 cost-stress runs. [protocol.json](protocol.json), [candidates.json](candidates.json), [training_leaderboard.csv](training_leaderboard.csv), [validation.csv](validation.csv), and [summary.json](summary.json) preserve the experiment. Signals are actual FinRL-X Adaptive Rotation / EqualWeightStrategy output, followed by the existing operational risk and simulated execution modules. This does not evaluate unavailable DRL or ensemble implementations.

## Selected research candidate — not a deployment recommendation

`{winner}`

| Setting | Value |
|---|---|
| Algorithm | Adaptive Rotation v1.2.2; top 2 per group |
| Rebalance | Monthly; protective checks each trading day |
| Initial capital / reinvest profits | $500 / yes |
| Maximum deployment / minimum cash reserve | 80% / 20% |
| Maximum position / sector | 25% / 50% |
| Maximum holdings / order size | 12 / $125 |
| Minimum order / fractional shares | $1 / enabled |
| Stop loss / trailing stop | 15% / 15% |
| Daily loss / peak drawdown / initial-capital loss triggers | 5% / 20% / 20% |
| Portfolio trigger response | Liquidate, then halt |
| Maximum rebalance turnover / daily orders | 75% / 15 |
| Annualized volatility target / eligibility cap | 45% / 85% |

The exact complete settings are in [recommended_research_settings.json](recommended_research_settings.json). Despite the filename, this is solely the candidate selected by the research rule. New variants also change holdings, turnover and liquidation rules relative to defaults; their improvement cannot be attributed to cadence alone. Loss triggers cannot cap realized losses through gaps or failed orders.

| Period | Candidate return | Candidate drawdown | SPY | QQQ |
|---|---:|---:|---:|---:|
{period_table}

The previously inspected 2025 interval was excluded from tuning, but is not represented as fully unseen. Strong 2022 defensive performance and 2024 validation performance did not carry into the untouched final period. Do not select a different configuration after inspecting that test and call its performance out of sample.

## Small-account trading costs

Base assumptions: 5 bps slippage plus half a 4 bps quoted spread on each side (7 bps adverse execution), no fixed or proportional commission, deterministic full fills, eligible fractional research units. Costs are embedded in fill prices. The exported `transaction_costs` metric contains explicit fees only; zero fees does **not** mean zero trading friction.

| Cost stress, same locked candidate and final dates | Ending value | Net return | Maximum drawdown | Orders |
|---|---:|---:|---:|---:|
{stress}

The $1 scenario paid $43 in explicit fees; cash constraints also changed sizing/order count. At $500, fixed per-order fees materially erode performance.

## Reproduce locally without credentials or network

From the repository root after installing `requirements-app.txt`:

```sh
python -m scripts.search_configurations --output runtime/reproduced-search
python -m scripts.report_configuration_search
```

The first command recomputes all simulations in a new output directory using the committed historical snapshots; it neither calls a broker nor edits deployed settings. It may take several minutes. Omit `--output` to resume already saved results. Use a fresh output directory after any code/configuration change; saved results are not automatically invalidated. The second command rebuilds the report/chart from the committed experiment results.

Training/validation/earlier-test prices use `sample_data/`; the final test uses [fresh_data/](fresh_data/), including raw vendor bars and per-file source/download-time/SHA-256 manifests. Downloads occurred on 2026-11-02 UTC. [artifact_hashes.json](artifact_hashes.json) fingerprints research inputs and relevant implementation files. The final-test normalized data hash is `{chosen["data_hash"]}`. Strategies only consume bars through the previous session; simulated fills occur at the following open. Final-test data includes earlier warmup bars, not just the evaluation dates.

## Verification

`pytest tests/test_configuration_search.py tests/test_core.py tests/test_api.py -q`: **40 passed in 47.74 seconds**, with 402 dependency deprecation warnings and no failures. [Full output](verification_tests.txt). The new tests check all candidate configurations and verify cached strategy signals reproduce the original backtester exactly. Ruff checks passed for the research scripts and test file.

An independent, uncached replay of the selected candidate on the committed final-period data exactly matched its data hash, all daily equity values, all orders, all decisions and all metrics. All 16 downloaded CSVs matched their vendor-download SHA-256 manifests. See [replay_verification.json](replay_verification.json). No UI code changed; UI tests were not rerun for this research task.

The standalone chart rendered all eight equity/drawdown traces in Chromium with networking disabled and no JavaScript errors; see [chart_verification.json](chart_verification.json).

## Limits and next decision

This is a constrained search, not an exhaustive optimum. It uses a current fixed universe with survivorship/selection bias, adjusted vendor data that may be revised, and daily monitoring rather than intraday execution. Adjustment factors approximate dividend reinvestment and use research share units. Each fold resets holdings/capital; these results are not a continuous live account. Multiple comparisons and a single validation year create overfitting risk. The final historical holdout was unseen by the selection process, but is still retrospective, not forward paper trading. No commission schedule or liquidity model has been verified against a user's broker.

Keep the deployed configuration unchanged. The next defensible experiment is a predeclared forward paper test, including buy-and-hold benchmarks, or a new strategy hypothesis evaluated on genuinely new data. Increasing aggressiveness or selecting the final-test winner after the fact would not establish a durable edge.
"""
    (ROOT / "REPORT.md").write_text(report)
    files = sorted((ROOT / "fresh_data").glob("*"))
    files += sorted(Path("sample_data").glob("*.csv"))
    files += sorted(Path("trader").glob("*.py"))
    files += sorted(Path("src/strategies/adaptive_rotation").rglob("*.py"))
    files += [
        Path("src/strategies/base_strategy.py"),
        Path("src/strategies/AdaptiveRotationConf_v1.2.2.yaml"),
        Path("scripts/search_configurations.py"),
    ]
    hashes = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()
    }
    (ROOT / "artifact_hashes.json").write_text(json.dumps(hashes, indent=2) + "\n")


if __name__ == "__main__":
    main()
