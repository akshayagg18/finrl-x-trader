# Implementation plan and upstream inspection
Upstream: AI4Finance-Foundation/FinRL-Trading, commit 4409abe925c904e570be78ebfb5e77ac3491dff8 (2026-11-02 clone).

1. Preserve upstream algorithms and isolate new operational service in `trader/`.
2. SQLite migrations, validated/versioned settings, immutable research runs, bot ownership ledger.
3. Genuine cached OHLCV, Adaptive Rotation bridge, equal-weight reference, explicit model readiness.
4. Common portfolio/risk/order pipeline; transactional simulator; SDK broker adapters; durable reconciliation.
5. Calendar-aware scheduler, local FastAPI dashboard, controls, settings, backtest comparison and exports.
6. Real-data replay, broker fault tests, UI tests, deployment and verification records.

## Inspected architecture
`src/strategies/base_strategy.py`: StrategyResult weights. `ml_strategy.py`: RF/GBM and optional LGBM/XGB rolling fundamental selection, equal/min-variance allocation. `ml_bucket_selection.py`: research ML buckets. `fundamental_portfolio_drl.py`, `rl_model.py`: rolling selection/FinRL DRL A2C/PPO/DDPG/TD3/SAC; require FinRL, external fundamentals and model training. `adaptive_rotation/`: config, preprocessing, regime, group IR, residual momentum rankings, portfolio builder, stops. `execution_engine.py`: signal-to-weight sizing. `backtest/backtest_engine.py`: bt weight-matrix backtest. `data/`: FMP/yfinance fetcher and SQLite store. `trading/alpaca_manager.py`: REST accounts, rebalance, rounding and orders. `web/app.py`: Streamlit with random/sample portfolio and backtest data. `main.py`: orchestration.

## Operational defects/limits to avoid
Upstream Alpaca rebalance sizes from whole account equity; can sell unrelated positions; price fallback $100 at lines 507/575; default $100 minimum; paper/live selection by account config. Existing backtester defaults $1m and integer shares. ExecutionManager defaults allow_short=True. Web sample statistics cannot serve as real performance. Adaptive exceptions TODO uses singleton Z-score history (persistence cannot trigger as published); ranker lookback uses top_n_per_group in engine initialization. New bridge corrects lookback from zscore_window and disables unimplemented historical exception persistence rather than claiming replication. Preserve source and disclose divergence. New central risk enforces stops on holdings independently.

## Published results
The +19.76% figure is upstream's publication, not an installation result. Exact deployed ensemble artifacts, point-in-time data snapshot and account fills are not supplied. No faithful reproduction claimed.
