# Engine comparison — retrieved 2026-11-03

| Engine | Relevant strengths | Integration costs / limits | Decision |
|---|---|---|---|
| [Freqtrade / FreqAI](https://www.freqtrade.io/en/stable/) | Crypto spot, backtesting, dry-run, exchange execution, ML retraining | GPL distribution obligations; exchange/region configuration and separate process ownership need review | Strong crypto alternative, not integrated yet |
| [LEAN](https://www.quantconnect.com/docs/v2/lean-engine/getting-started) | Multi-asset event engine, brokerage integrations, fill/fee/settlement models | .NET runtime and data conversion; local engine does not grant historical data entitlements | Strong equity alternative; not integrated |
| [NautilusTrader](https://nautilustrader.io/docs/latest/) | Python interface, compiled execution engine, cash accounts, deterministic event replay, real fills/account state | Version-specific instrument adapters; equity quantity precision needs separate fractional support; broker integration still work | Selected for the initial shared research subsystem, pinned 1.231.0 |
| [Jesse](https://github.com/jesse-ai/jesse) | Crypto strategy development/backtesting | Live component availability and licensing must be checked separately | Not integrated |
| [Hummingbot](https://hummingbot.org/) | Connector ecosystem and market-making infrastructure | Requires realistic order books and fill probabilities; candle-only maker results would be misleading | Not selected for initial candle research |
| [FinRL-X](https://github.com/AI4Finance-Foundation/FinRL-Trading) | Existing portfolio allocation, research, dashboard, broker interfaces | Current wrapper uses daily/weekly signals; does not imply intraday support | Preserved as separate existing subsystem |

The Nautilus integration uses actual BacktestEngine, CASH venues, instrument quantity precision, market-order submission, fees and account balances. It does not replace order execution with arithmetic-only return calculations. Bid/ask ticks are **modeled execution quotes derived from historical opens**, not historical quote observations. Full fills and deep liquidity remain assumptions. Production adapters and the central account-level risk/orchestration integration are unfinished. Installing Nautilus does not make those capabilities operational.

This is a preliminary engineering comparison. Project licenses, maintenance commits and external connector behavior have not yet received a complete compatibility audit. Do not treat this table as completed production due diligence.
