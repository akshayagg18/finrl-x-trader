# Preliminary intraday backtest results

Genuine historical bars; NautilusTrader 1.231.0; $500 starting capital. Common final test: 2026-10-01 through 2026-10-30. Configurations selected on earlier validation data.

| Instrument | Selected net return | Ending equity | Drawdown | Fills | Gross scenario | 2× costs |
|---|---:|---:|---:|---:|---:|---:|
| BTC-USDT | -14.19% | $429.07 | -15.02% | 90 | -4.41% | -15.09% |
| ETH-USDT | -15.40% | $423.01 | -15.40% | 90 | -7.53% | -15.33% |
| AAPL | -0.12% | $499.38 | -2.25% | 36 | 0.58% | -0.90% |
| SPY | 0.00% | $500.00 | 0.00% | 0 | 0.00% | 0.00% |
| QQQ | 0.00% | $500.00 | 0.00% | 0 | 0.00% | 0.00% |

**NO QUALIFIED LIVE STRATEGY.** Positive short-period results, if any, are not sufficient evidence.

The gross scenario reruns without costs; changed sizing and halt times mean it is not a fee add-back to identical trades. Crypto is denominated in USDT assuming USD parity. Equity costs are estimates, not the actual IBKR minimum-fee schedule. SPY/QQQ produce no orders where whole-share prices exceed the allocation. Those zero returns are cash outcomes, not successful ETF trading.

Buy-and-hold controls retain the same 80% deployment cap, trade once on entry and exit at the final mark, and bypass stops. Cash earns no interest. All endpoints are marked using modeled adverse bid/ask quotes; fills assume sufficient liquidity. Stops are evaluated at bar boundaries. No historical spread/depth data was obtained.

The 90 runs comprise six parameter candidates × two development periods × five symbols, then six final-test scenarios × five symbols. Exact protocol, locked selections, settings, fill records and equity paths are under `research/intraday/results/`. Two years of crypto data were obtained; equities cover only about 60 sessions. Data manifests are under `research/intraday/data/`.

Limitations: no ML comparison, no 5-minute evaluation, no full walk-forward study, no complete trade-statistics or regime report, no settlement-aware fractional equity execution, no fee-account verification. The current data and execution assumptions cannot qualify a live strategy.
