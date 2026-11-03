"""Report actual saved walk-forward results, including zero-trade outcomes."""

import gzip
import importlib.metadata
import json
from pathlib import Path

import pandas as pd

from trader.intraday.analytics import analyze

root = Path("research/intraday_ml")
rows = json.loads((root / "summary.json").read_text())
frame = pd.DataFrame(rows)
frame.to_csv(root / "comparison.csv", index=False)
lines = [
    "# Machine-learning evaluation — 2026-11-03",
    "\n**NO QUALIFIED LIVE STRATEGY.** Models were built and tested; consistent after-cost profitability was not demonstrated.",
    "\nRandom forest and histogram gradient boosting regress future open-to-open returns. Inputs are lagged returns, realized volatility, rolling deviations, range, volume and time-of-day. All labels mature before training cutoff; random train/test splitting is prohibited. An expected-return threshold includes round-trip fees, adverse execution and a selected extra buffer. Horizon/cooldown rules limit turnover.",
    "\nSelection: train before 2025-07-01; validate July–August 2025. Eight configurations per symbol/interval (2 families × 2 horizons × 2 buffers), 32 validation scenarios total. Lock highest validation return subject to observed drawdown better than -15%, then refit that family/horizon before each subsequent test. Four symbol/interval combinations × 3 test windows × 7 scenarios = 84 walk-forward backtests, **116 evaluations total**.",
    "\nEach fold starts independently with $500; default deployment ceiling 50%, 10 bps fee + 5 bps adverse execution per side. These are global spot research assumptions, not a verified Singapore account tariff. Holding cash earns no interest. Hold comparisons invest the same 50%, bypass stops, and liquidate at period end. USDT/USD parity is assumed.",
    "\n| Market | Interval | Jan–Feb 2026 ML | Jul–Aug 2026 ML | October 2026 ML | Fills across folds |",
    "|---|---:|---:|---:|---:|---:|",
]
for (symbol, interval), g in frame[frame["case"] == "ml"].groupby(
    ["symbol", "interval"]
):
    g = g.sort_values("start")
    lines.append(
        f"| {symbol} | {interval}m | {g.iloc[0]['return']:+.3%} | {g.iloc[1]['return']:+.3%} | {g.iloc[2]['return']:+.3%} | {int(g.fills.sum())} |"
    )
lines += [
    "\nAll selected models placed zero October trades. That is abstention, not a profitable trading result. The small positive BTC periods had few fills and do not establish an edge. Avoid tuning again on these results and presenting the same periods as untouched.",
    "\nOctober baseline performance was already inspected in earlier work; it is excluded from model fitting/selection but is **not a pristine research holdout**. These are retrospective tests, not prospective paper profits. The much shorter equity history is not used to claim an equity ML advantage.",
    "\nFull net/gross/1.5×/2× costs and cash/hold/momentum comparisons: [comparison.csv](comparison.csv). Compressed JSON files contain actual execution fills and equity curves. Per-exit statistics, fees, turnover, holding time, downside metrics and worst losing streak: [analytics.csv](analytics.csv). Risk ratios use daily observations, not inflated intrabar annualization. Yearly returns are omitted for short periods. Gross scenarios are independently rerun, so costs can change sizing and halt behavior.",
    "\nModels and frozen data are content-hashed. Runtime model artifacts stay local, outside Git; recreate with `python -m scripts.benchmark_ml`, or train/select versions through the dashboard. Only locally created hash-verified artifacts may be loaded. `environment.json` records package versions.",
    "\n## Continuous simulation and remaining external gates",
    "\nThe existing scheduler now advances isolated, persistent historical replay sessions. Nautilus preserves continuous holdings through deterministic reconstruction without cycle-end liquidation. Atomic SQLite cycles and fill identities prevent duplicate saved trades. Pause blocks entries while stops/exits continue; Stop suspends monitoring; liquidation runs at the next simulated bar. This accelerated replay is neither a streaming market-data paper account nor a brokerage account.",
    "\nThe shared portfolio-loss gate covers daily, peak and initial-capital losses. Equity sale proceeds are withheld until the next exchange session; original settled cash remains usable. Single-instrument sessions have immutable configuration and isolated virtual capital. Sessions do not share funds with existing swing strategies or manually held assets.",
    "\nThe CCXT OKX spot transport implements balances, positions, instruments, quotes, order lookup/cancellation/fills and guarded market submission. Missing credentials, regional verification and authorization fail closed. Transport timeouts are ambiguous and never retried automatically. It is **not wired to the intraday live scheduler**, and Singapore account eligibility/endpoint plus broker-reported fills remain externally unverified. Full multi-market live risk/ownership routing and fractional equity execution remain unfinished implementation. No real orders were submitted.",
    "\nRecommendation: retain cash/default-disabled live trading. Use the completed replay and training tools to conduct predeclared new experiments or a prospective paper study; do not present any tested model as proven profitable.",
]
(root / "REPORT.md").write_text("\n".join(lines) + "\n")
analytics = []
for path in root.glob("*.json.gz"):
    with gzip.open(path, "rt") as f:
        r = json.load(f)
    analytics.append({"run": path.name, **analyze(r)})
pd.DataFrame(analytics).to_csv(root / "analytics.csv", index=False)
(root / "environment.json").write_text(
    json.dumps(
        {
            p: importlib.metadata.version(p)
            for p in [
                "nautilus_trader",
                "scikit-learn",
                "pandas",
                "numpy",
                "ccxt",
                "joblib",
            ]
        },
        indent=2,
    )
)
modeldir = Path("runtime/intraday_models")
(root / "model_manifest.json").write_text(
    json.dumps(
        {p.stem: json.loads(p.read_text()) for p in modeldir.glob("*.json")}, indent=2
    )
)
print("\n".join(lines[5:12]))
