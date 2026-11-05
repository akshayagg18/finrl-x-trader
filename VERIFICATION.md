# Verification and readiness

Tested 2026-11-02 in this Linux/Python 3.12 workspace. Source: actual upstream commit `4409abe925c904e570be78ebfb5e77ac3491dff8`. No broker credentials were requested, supplied or used. **No real or brokerage-paper orders were submitted.**

This installation is a working local application. It does **not** meet every requested production criterion; the gaps below are explicitly unfinished, not implied to be solved by entering API keys.

## Executed verification

- `python -m pytest -q --junitxml=artifacts/test-results.xml`: **39 passed in 42.49 seconds**. See [raw test output](artifacts/tests.txt) and [JUnit report](artifacts/test-results.xml). The suite uses broker doubles only for external orders and a real Chromium browser for UI verification.
- `ruff check trader tests scripts --select F`: passed. Formatting applied to new Python code. `git diff --check`: passed.
- Application started without credentials; `/`, `/api/health`, settings, overview and locally hosted chart assets responded. Local server: `http://127.0.0.1:8765`.
- Chromium tested: changing a risk setting, save/validation, full reload and persisted setting; executing a real-data local cycle; resulting orders and holdings; symbol search; running an actual backtest and rendering its results. Desktop and mobile screenshots saved under `artifacts/`.
- Docker image `finrl-console:local` built successfully; Compose configuration validated. Unprivileged, read-only container started on loopback port 8766 and returned health status `ok`. Disk exhaustion during the first container-start attempt was resolved by deleting this task's temporary extraction and superseded build cache, then retrying. The current Docker image and local source are retained. A genuine three-order local replay also ran inside the container; all three orders and positions persisted across a container restart. See artifacts/docker-verification.json.
- A local replay and full default historical backtest were generated and saved in `runtime/trader.db`, not hardcoded in the UI. `scripts/verify.py` reproduces the record; [verification.json](artifacts/verification.json) has exact targets, fills, metrics, data hash and assumptions. This replay database contains virtual history, not a real account.

### Genuine $500 historical replay

Execution date 2025-01-06; signal uses completed data through 2025-01-03. Actual upstream Adaptive Rotation produced NVDA/AMZN/JPM/GS target weights of 25% each. Central risk reduced weights according to volatility/deployment limits. Turnover and per-order constraints limited execution to three fractional buys:

| Symbol | Simulated filled quantity | Simulated fill price, adjusted research basis |
|---|---:|---:|
| AMZN | 0.439768 | $226.938746 |
| GS | 0.173105 | $576.529222 |
| JPM | 0.210689 | $240.043184 |

Cash remaining: **$249.825052**. Simulated immediate mark-to-market is slightly below $500 because adverse spread/slippage are included. Commissions are configured to zero, not asserted to always be zero at brokers. Holdings, orders and cash survived re-opening the database. Repeating the cycle returned the prior cycle without duplicate orders. No NVDA order was fabricated when turnover capacity was exhausted.

### Genuine historical evaluation

Default Adaptive Rotation, $500, configured universe, 2025-01-02 through 2025-10-07:

- 191 daily observations; 145 simulated order records.
- Total time-weighted return **+0.7367%**.
- Maximum drawdown **-11.9389%**.
- Sharpe **+0.1453** with zero risk-free rate.
- Out-of-sample boundary 2025-07-01; subsequent interval return **+4.3655%**.
- 5 bp adverse slippage + half a 4 bp spread per side; zero configured commissions. Fractional adjusted research units. Fully invested SPY/QQQ benchmark entry costs included.
- Annualized return omitted because there are fewer than 252 observations. Win rate is based on realized sale fills, not a fabricated count of complete round trips.

An earlier run before the final conservative holdings-cap fix returned −1.1229%; that prior research run remains saved as run #1. The figures above are the final implementation’s run #2. This illustrates the sensitivity to execution constraints, not a strategy optimization claim.

These are estimates from this installation's specific settings and historical vendor snapshot. The fixed selected universe, vendor revisions, adjusted-price normalization, approximate dividends, execution assumptions and lack of certified vintage data limit interpretation. This is not evidence of expected live profitability. The upstream published **+19.76%** was not reproduced or relabeled as our result; exact deployed ensemble artifacts and fills are absent.

## Automated coverage

| Area | What was exercised |
|---|---|
| Configuration | Defaults, validation, invalid modes/ranges/NaN, unknown keys, settings versions and persistence |
| Credentials | Missing Alpaca paper/live keys; paper credentials do not enable live |
| Local execution | Fractional rounding, $1 minimum behavior, filled/rejected/partial orders, commissions, cash and ownership |
| Portfolio/risk | Position/sector/volatility caps, budget isolation from larger account cash, daily/capital/drawdown triggers, protective stops, insufficient cash and unowned sell rejection |
| Market data | Genuine bundled bars, invalid/missing/stale data, common-session warmup, future-price perturbation leaves earlier strategy weights unchanged |
| Recovery | Settings/positions survive service reconstruction, duplicate cycle IDs, cumulative partial fills applied once, timeout leaves durable intent, interrupted cycle cannot blindly retry |
| External brokers | Alpaca SDK request contract, DAY fractional orders, partial/rejected status normalization, market-closed check and timeout propagation; IBKR mode guards and commission/fill normalization |
| Account isolation | Broker/ledger switching keeps ownership separate; unowned holdings and ambiguous orders halt reconciliation |
| Scheduler | Persistent start/pause state, market sessions/holiday/DST/early close, paused monitoring request and next-operation state |
| Performance | Time-weighted cash-flow correction, drawdown, short-sample labels, daily aggregation of intraday observations |
| Backtesting | Deterministic repeated runs, shared cost/sizing/risk modules, costs deducted, OOS reporting, benchmarks and research/trading history separation |
| Models | Actual upstream RF/GBM rolling training, model artifact and feature metadata saved, uncertified research model refused for deployment |
| API/browser | Local host/origin/header guards, secret-bearing exceptions not returned/audited, settings save/reload, simulation, fills/holdings/search, backtest rendering, backup/export |

Warnings: dependency deprecation messages from NumPy/Pandas/exchange-calendars, Starlette TestClient/httpx and websockets; no test failures. The dependency ranges and tested versions should be revalidated before upgrades.

## Requires external credentials/session verification

- **Alpaca**: real connection permissions, IEX quote availability, instrument flags, account restrictions, actual order acceptance, partial-fill/cancellation races, rate limits, outages, execution quality and overnight reconciliation. The official SDK adapter and mock contracts exist; successful live/paper execution has not been claimed.
- **IBKR**: authenticated Gateway/TWS, socket reachability, client ID, account summary fields, contract/order permissions, market data entitlement, commission timing, reconnect and completed-order recovery. Whole-share adapter only. `IBKR_CONNECTED_VERIFIED` defaults false until external verification. A $500 account may produce no permissible whole-share trades.
- **Long-running operations**: multi-day unattended stability, broker maintenance windows and emergency liquidation during real market stress have not been established by short automated tests.

## Unfinished implementation and important limits

1. **DRL deployment/training**: upstream research scripts are preserved and identified, but the custom FinRL environment/dependency/observation pipeline is not integrated as a working dashboard strategy. No trained DRL artifact is supplied. This is implementation work, not merely missing credentials.
2. **Published ensemble**: exact deployed Rolling + Rotation ensemble combiner/artifacts are not provided upstream. No imitation combiner is presented as equivalent. It is unavailable.
3. **ML deployment and automated retraining**: real upstream RF/GBM research training and artifact persistence work. Optional LightGBM/XGBoost require their libraries. The bundled fundamentals have accepted dates but not certified vintage provenance/historical membership. Broker deployment, rolling inference evaluation and scheduled retraining are blocked/unfinished. The UI says research-only and refuses promotion. Deterministic Adaptive Rotation/Equal Weight snapshots can be deployed and rolled back.
4. **Exact live net accounting**: Alpaca order objects lack full account-activity fees. The adapter currently records zero fee on its fills; regulatory/activity fees and dividends are not attributed. Actual broker net performance is therefore not fully implemented. IBKR uses reported commission data but delayed commissions after an already terminal order are not automatically revisited. Broker statement reconciliation remains necessary.
5. **Corporate actions / deposits**: splits and dividends are approximated through adjusted historical research units in local/backtests. Live split/share changes halt on mismatch; automatic live corporate-action handling is unfinished. Automatic external deposit/withdrawal detection is not implemented; enabling external `include_deposits` fails validation. Explicit allocated-budget changes are supported and accounted as flows. Percentage allocation is captured at initial binding with a dollar cap, not continuously recalculated from external equity.
6. **Shared accounts**: unsupported by design. Dedicated account required; manual holdings/orders are never sold/imported. Unexpected broker changes fail closed. Cash reconciliation is a conservative available-cash check, not a complete independent broker cash-flow audit.
7. **Historical fidelity**: static universe causes selection/survivorship bias; vendor-adjusted/revised prices are not vintage-certified. OOS reporting and t-1 execution eliminate direct future-bar use but do not prove the dataset is free of every revision bias. Adaptive upstream exception persistence has a singleton-history TODO; the bridge corrects ranker lookback and supplies daily fast-risk-off data but does not pretend to restore missing historical exception state.
8. **Order/scheduler limits**: market DAY orders only. Stops are monitored by the application, not guaranteed broker-native protective orders. Protective reductions bypass turnover but still obey per-order and daily order-count limits. Minimum-order dust can remain. An unresolved crash/submission intentionally requires operator review; there is no unsafe automatic retry. Local historical replay is manual; autonomous local operation requires fresh current data. Scheduler loop does not run when the process is stopped.
9. **Infrastructure**: single-host, one-worker SQLite application. Local-only host/origin guards, not a remote authentication product. No external alert delivery, HA failover, independent watchdog, penetration audit or Windows runtime execution was performed. Windows instructions are provided but unverified here. Dashboard comparisons use cached benchmarks and may be absent outside cached coverage.
10. **Research UI**: common deployed risk/cost/universe settings can be changed and used by a backtest; independent per-run settings are retained with each result. Interactive price-level position charts and full entry/exit price charts per instrument are not implemented; backtests show trade markers on portfolio equity and the dashboard shows per-position P&L. The plugin interface is defined, with no paid AI signals registered.

The application is ready for local research/simulation and later adapter connection work. It should not be described as a fully verified production autonomous money manager while these gaps remain.

## Intraday research extension — 2026-11-03

**Partial implementation, not completed autonomous intraday trading.** Added NautilusTrader 1.231.0 historical cash-account execution, real 15-minute datasets, configurable momentum/reversion/cash/hold experiments, cost sensitivity, persisted API results and an intraday panel in the existing dashboard. No real orders or broker paper-account orders were submitted. Original FinRL-X functionality remains separate.

Executed 90 unique development/test scenarios. BTC and ETH each have 70,080 consecutive 15-minute bars (2024-11-01–2026-10-31), no duplicate timestamps or missing intervals. AAPL/SPY/QQQ each have 1,560 regular-session bars after calendar filtering, approximately 60 trading sessions. Source/download/hash manifests accompany raw CSVs. Crypto instruments use retrieved lot/tick/minimum metadata; current equity engine integration enforces whole shares. Candle-based modeled quotes are not historical observed quotes. USDT/USD parity is an assumption.

Tests: `PLAYWRIGHT_BROWSERS_PATH=/workspace/pw-browsers .venv/bin/pytest tests/test_intraday.py tests/test_core.py tests/test_api.py tests/test_ui.py -q` — **45 passed, 880 dependency deprecation warnings, 45.39 seconds**. Includes original application regression/browser workflows plus intraday configuration persistence, real-data order fills, no future-bar signal influence, fees, capital isolation and whole-share affordability. Browser test executes the intraday research workflow and reloads saved settings. Full output: `research/intraday/verification_tests.txt`.

Remaining implementation, not merely credential verification: continuous intraday simulation and scheduler recovery; shared intraday/portfolio risk enforcement; a true settled-funds ledger; fractional equity instrument handling; private crypto execution; ML/FreqAI training/model versions; 5-minute and walk-forward evaluation; full regime/trade analytics; intraday broker failure/partial-fill/reconciliation tests. No claim of production readiness. External blockers: Singapore account eligibility and regional exchange API/fees, broker transition policies, credentials and better equity/quote data.

`research/FINAL_RECOMMENDATION.md` explicitly reports **NO QUALIFIED LIVE STRATEGY**. Existing live settings were not activated or changed.

## ML / persistent intraday replay continuation — 2026-11-03

This update supersedes the earlier ML, five-minute data, settlement and continuous local replay limitations. Random forest and histogram gradient boosting now train with lagged features, purged label maturity and immutable model manifests. Two years each of 5-minute BTC/ETH data complement the 15-minute snapshots. The locked study completed **32 validation scenarios plus 84 walk-forward scenarios**. It did not qualify a live model; some positive windows had very few trades and October selections had none. See `research/intraday_ml/REPORT.md` for actual results and previously-inspected-test caveats.

Continuous **local historical replay** now runs under the existing scheduler. Positions remain open across cycles; no repeated forced liquidation. Immutable data/configuration, process locks, atomic SQLite checkpoints and stable fill identities enable restart recovery without duplicate saved execution. Pause, resume, stop and simulated liquidation work. Global kill stops replay. One active intraday session owns a separate virtual allocation; it never spends brokerage funds. The independent portfolio-loss gate is shared with daily strategies. Equity unsettled sale proceeds mature at the next exchange session.

Full command: `PLAYWRIGHT_BROWSERS_PATH=/workspace/pw-browsers .venv/bin/pytest tests -q` — **56 passed, 3,546 dependency deprecation warnings in 53.30 seconds**. Tests cover original core/API/browser flows plus ML feature causality, label maturity, artifact integrity, invalid configuration, ownership isolation, position continuity, restart recovery, duplicate fills, pause/liquidation, global kill, scheduler restoration, settlement weekend handling, missing exchange credentials, uncertain submission without retries and browser replay persistence. Ruff checks for new modules/scripts/tests and `git diff --check` passed. Full log: `research/intraday_ml/verification_tests.txt`.

Remaining: intraday external paper/live orchestration, shared *external-account* ownership/risk routing, fractional equity instrument support, live-feed simulation and external broker/exchange verification. CCXT transport methods are implemented/mock-tested but deliberately not connected to the replay scheduler. Models and fills are historical research, not verified paper-account profits. No real orders or credentials were used. Live remains disabled by default.

## Growth / weekly-consistency plan — 2026-11-03

Implemented a separate hourly BTC/ETH research pipeline with 4/24/72-hour net-return labels, nine-month training, three-month calibration/validation, two model families and two confidence thresholds. Logged 288 monthly candidate trials; exactly one passed the stricter validation gates. Six continuous $500 portfolio scenarios retain holdings, cash and peak equity across monthly decisions. The selected policy lost 3.35%, with 3.50% maximum drawdown and 17 completed exits; no policy qualified. Raw trials, decisions, fills, equity, cost attribution, Singapore-week statistics and bootstrap gates are in `research/growth/`.

New forward simulation uses public timestamped quotes, separate persistent SQLite state, hourly buckets, immutable financial settings, atomic records and stable fill identifiers. A new genuine quote check was completed without keys: BTC/ETH bid/ask observed at 2026-11-03 09:51 UTC; $500 cash and zero trades. The verification account was stopped. Missing/late monthly model validation, stale quotes, outages and global kill fail closed. This remains local modeled execution, not actual exchange fills. Model promotion is blocked without passing historical evidence, and is separately logged without resetting account history.

Qualification requires 52 complete historical weeks/100 exits plus return, drawdown, doubled-cost and confidence conditions, followed by at least 12 complete forward weeks/30 exits. The current dataset supplies 51 complete evaluation weeks after excluding partial boundaries and the selected account loses money, so there is no qualification. Historical periods were previously inspected; this is development evidence. The real forward observation requirement cannot be completed immediately.

Existing broker routing, private credentials and live activation were not changed. Runtime model binaries and account databases are excluded from Git. Reproduce via `python -m scripts.evaluate_growth`; run with the existing `python -m trader serve` command. Forward quote sampling and risk monitoring are hourly; gaps can exceed stops. Full fills and deep liquidity are assumptions; fees and USDT/USD parity are unverified account-specific assumptions. Existing swing/intraday research remains accessible independently.

Final regression command: `PLAYWRIGHT_BROWSERS_PATH=/workspace/pw-browsers .venv/bin/pytest tests -q` — **67 passed, 4,948 dependency deprecation warnings in 55.77 seconds**. New coverage includes hourly aggregation, label maturity/feature causality, continuous month-boundary holdings, entry limits, same-trade cost attribution, Singapore weekly boundaries, sparse-sample rejection, forward restart/deduplication, frozen settings, outages, stale quotes, qualification-gated promotion and dashboard configuration/start/stop persistence. Ruff and whitespace checks passed. Full log: `research/growth/verification_tests.txt`.

## Long-history regime and ML verification — 2026-11-05

The new experiment uses 80,581 genuine public hourly rows per asset from Binance
archives (BTCUSDT and ETHUSDT, August 2017 through October 2026). Per-month URLs,
HTTP metadata and SHA-256 hashes are retained. Reindexing exposes 170 missing
standard hours; 43 irregular partial bars are recorded and excluded from the
standard hourly feature grid. Incomplete daily/four-hour windows cannot become
valid completed-bar features.

The protocol was serialized and hashed before the final period was evaluated.
All eight base rules failed the untouched 2022 gate. The selected diagnostic
rule (`trend_20_100_mom_24_q80`) returned +11.27% in 2019–2021 and −1.65% in
2022. The four fixed ML filters also lost in 2022; the selected diagnostic
forest/0.60 filter returned −1.35% there.

On the untouched 2023–October 2026 diagnostic interval, the rule returned
−6.45% and triggered the 8% drawdown halt. The ML-filtered variant returned
−1.77% at assumed costs, −6.07% at 1.5x costs, and −6.08% at doubled costs. It
had 197 completed exits and a negative lower 95% weekly-mean bound, so it failed
qualification. A 60%-deployed hold benchmark returned +136.93% with a −52.35%
maximum drawdown. No research result was promoted, and no external order was
submitted.

Focused tests cover source/hash integrity, explicit gaps, feature causality,
incomplete-window rejection, label maturity, entry-only ML filtering, protective
stop reset, nonleveraged signals, selection-lock integrity, failed qualification,
annual-refit history continuity, and dashboard rendering.

Final regression command:
`PLAYWRIGHT_BROWSERS_PATH=/workspace/pw-browsers .venv/bin/pytest tests -q` —
**82 passed, 4,970 dependency deprecation warnings in 60.70 seconds**. The saved
output is `research/strategy_v2/verification_tests.txt`. Ruff, whitespace, and
credential-pattern checks passed.

The combined optional stack has unresolved declared dependency bounds:
CCXT/Nautilus require `cffi==2.0.0`/`tzdata>=2026.3`, while curl-cffi/ib-async
declare `cffi>=2.1.1`/`tzdata<2026`. The recorded suite passed with the former
versions. Treat IBKR and CCXT as separate externally verified deployment
profiles until their pinned packages can share a clean resolver environment.

## Defensive trend search — 5 November 2026

The new low-exposure search evaluates 81 fixed BTC/ETH trend configurations on
the hash-verified Binance hourly archive. Fourteen passed the development and
validation gates. The validation-ranked rule is a weekly 100-day BTC trend plus
90-day momentum gate, with no more than 10% in either asset, 20% total exposure,
and volatility scaling toward a 30% annualized target.

Measured after 15 bp per traded notional, the selected rule returned +6.98%
with -1.23% drawdown in 2019–2021, +4.73% with -3.28% drawdown in 2022–2023,
and +2.84% with -9.67% drawdown in 2024–October 2026. Doubling costs produced
+2.31% with -9.86% drawdown. A 10% BTC / 10% ETH passive comparison returned
+8.20% in the last period but drew down -22.51%.

Across 29 independent two-month reset windows from January 2022 through
October 2026, the rule averaged +0.20% ($0.98), with -1.23% average maximum
drawdown: 10 windows gained, 9 lost and 10 were flat. Evaluation included 146
complete weeks; 44 gained, 39 lost and 63 were flat. The lower 95% block-
bootstrap weekly-mean bound was -0.10%, so weekly consistency is not
established.

The candidate is labeled historically profitable and deployment unqualified.
The final interval was already inspected in exploratory work, the search has
multiple-testing risk, account-specific costs/fills remain unverified, and no
new 12-week paper observation exists. Artifacts and limitations are in
`research/defensive_trend/`. No external order was submitted and live trading
remains disabled.

Final regression command:
`PLAYWRIGHT_BROWSERS_PATH=/workspace/pw-browsers .venv/bin/pytest tests -q` —
**88 passed, 4,971 dependency deprecation warnings in 61.50 seconds**. The log is
`research/defensive_trend/verification_tests.txt`. Focused defensive tests cover
feature causality, stable calendar cadence, allocation caps, BTC gating, cost
monotonicity, protocol hashing and explicit deployment blocking. The browser
test verifies that the dashboard renders the historical and deployment states.
