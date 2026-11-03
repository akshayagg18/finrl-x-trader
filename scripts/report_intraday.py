import json
from pathlib import Path

import pandas as pd

ROOT = Path("research/intraday/results")
rows = json.loads((ROOT / "summary.json").read_text())
brief = pd.DataFrame([{k: v for k, v in r.items() if k != "config"} for r in rows])
brief.to_csv(ROOT / "comparison.csv", index=False)
lines = [
    "# Preliminary intraday backtest results\n",
    "Genuine historical bars; NautilusTrader 1.231.0; $500 starting capital. Common final test: 2026-10-01 through 2026-10-30. Configurations selected on earlier validation data.\n",
    "| Instrument | Selected net return | Ending equity | Drawdown | Fills | Gross scenario | 2× costs |",
    "|---|---:|---:|---:|---:|---:|---:|",
]
for symbol in ["BTC-USDT", "ETH-USDT", "AAPL", "SPY", "QQQ"]:
    r = next(x for x in rows if x["symbol"] == symbol and x["case"] == "selected")
    g = next(x for x in rows if x["symbol"] == symbol and x["case"] == "gross")
    s = next(x for x in rows if x["symbol"] == symbol and x["case"] == "cost_2x")
    lines.append(
        f"| {symbol} | {r['net_return']:.2%} | ${r['ending_equity']:.2f} | {r['max_drawdown']:.2%} | {r['fills']} | {g['net_return']:.2%} | {s['net_return']:.2%} |"
    )
lines += [
    "\n**NO QUALIFIED LIVE STRATEGY.** Positive short-period results, if any, are not sufficient evidence.",
    "\nThe gross scenario reruns without costs; changed sizing and halt times mean it is not a fee add-back to identical trades. Crypto is denominated in USDT assuming USD parity. Equity costs are estimates, not the actual IBKR minimum-fee schedule. SPY/QQQ produce no orders where whole-share prices exceed the allocation. Those zero returns are cash outcomes, not successful ETF trading.",
    "\nBuy-and-hold controls retain the same 80% deployment cap, trade once on entry and exit at the final mark, and bypass stops. Cash earns no interest. All endpoints are marked using modeled adverse bid/ask quotes; fills assume sufficient liquidity. Stops are evaluated at bar boundaries. No historical spread/depth data was obtained.",
    "\nThe 90 runs comprise six parameter candidates × two development periods × five symbols, then six final-test scenarios × five symbols. Exact protocol, locked selections, settings, fill records and equity paths are under `research/intraday/results/`. Two years of crypto data were obtained; equities cover only about 60 sessions. Data manifests are under `research/intraday/data/`.",
    "\nLimitations: no ML comparison, no 5-minute evaluation, no full walk-forward study, no complete trade-statistics or regime report, no settlement-aware fractional equity execution, no fee-account verification. The current data and execution assumptions cannot qualify a live strategy.",
]
Path("research/BACKTEST_RESULTS.md").write_text("\n".join(lines) + "\n")
Path("research/FINAL_RECOMMENDATION.md").write_text("""# NO QUALIFIED LIVE STRATEGY

No market/strategy is recommended for live deployment from this experiment. Crypto has the stronger free historical-data coverage; that does not establish stronger net performance or Singapore account access. The actual measured comparison is in [BACKTEST_RESULTS.md](BACKTEST_RESULTS.md).

NautilusTrader is integrated for isolated historical research. Existing FinRL-X swing strategies remain available. Global OKX public data is functional; a Singapore private trading adapter is not implemented or verified. Alpaca and IBKR remain the original application's separate adapters, not verified intraday routes. No winner broker is selected without residency, account and tariff checks.

Recurring software subscription costs are zero for this local research subsystem; electricity, hosting, data entitlements, currency conversion, fees and taxes are additional and account-dependent. The final test is only one month. No evidence here justifies a real-money test. Keep live execution disabled.

The full requested autonomous intraday application is **not complete**. Continuous paper simulation/scheduling, central cross-market capital/risk ownership, private crypto execution, ML, extended metrics and comprehensive operational tests remain implementation work, not merely missing credentials.
""")
print("\n".join(lines[:9]))
