# FinRL-X self-hosted trading console

**New contributor or agent? Start with [HANDOFF_CURRENT_STATE.md](HANDOFF_CURRENT_STATE.md)** for the consolidated current state, actual results, setup, known gaps and prioritized next steps.

## Defensive trend candidate (5 November 2026)

The latest locked search found a **historically profitable, low-exposure
candidate** on BTC/ETH spot history. It is not qualified for broker deployment.
The rule checks a lagged 100-day BTC trend and 90-day momentum each Monday,
deploys at most 10% to BTC and 10% to ETH, volatility-scales those weights, and
keeps at least 80% cash. Across separate 2019–2021 development, 2022–2023
validation, and 2024–October 2026 evaluation partitions it returned +6.98%,
+4.73%, and +2.84% after modeled costs. Doubled evaluation costs produced
+2.31%; evaluation maximum drawdown was -9.67%.

This is modest retrospective performance. The same-risk passive comparator
returned +8.20% in the evaluation period but breached the risk tolerance with a
-22.51% drawdown. The candidate's lower 95% weekly-mean bound is negative, only
44 of 146 complete evaluation weeks gained, and the final interval had already
been inspected during exploration. It therefore remains research only. Read the
[full report](research/defensive_trend/REPORT.md) and reproduce it without
credentials:

```sh
python -m scripts.evaluate_defensive_trend
```

### 20% and 50% drawdown frontier

The follow-up [drawdown-frontier report](research/drawdown_frontier/REPORT.md)
tests 162 tier/configuration combinations. The 20% tier allows up to 20% per
asset and 40% total exposure; it returned +5.04% in the 2024–October 2026
diagnostic evaluation with -18.54% drawdown, or +3.97% with doubled costs. The
50% tier allows up to 50% per asset and 100% total exposure; it returned +7.50%
with -40.87% drawdown, or +4.79% with doubled costs.

The 50% tier is not preferred: compared with the 20% tier, it added only 2.46
percentage points of return while worsening drawdown by 22.33 percentage
points. Both use previously inspected history and remain blocked from broker
deployment. Reproduce with `python -m scripts.evaluate_drawdown_frontier`.

### Short, market-neutral, and protective-put research

The [four-track comparison](research/hedge_comparison/REPORT.md) brings three
hedging alternatives through the same development, validation, evaluation,
cost-stress, weekly, and independent two-month workflow as long/cash:

- A BTC short overlay failed the 2024–October 2026 evaluation at every tier:
  -0.72%, -2.18%, and -10.60% before stress.
- BTC/ETH market-neutral relative value also failed: -1.23%, -2.79%, and
  -9.31%; doubled carry and friction worsened the losses.
- Synthetic protective puts reduced drawdown only slightly. The 10% tier made
  +1.94% versus +2.84% unhedged and barely stayed positive under stress at
  +0.28%. The 20% and 50% put tiers lost money under stress.

Long/cash remains the best historical candidate at all three risk tiers. No
track is deployment qualified. Short legs use spot prices as derivative proxies
with 10% annual carry; puts use Black-Scholes marks from lagged realized
volatility because historical option chains are unavailable. Reproduce with:

```sh
python -m scripts.evaluate_short_hedge
python -m scripts.evaluate_relative_value
python -m scripts.evaluate_put_protection
python -m scripts.report_hedge_comparison
```

### Selected autonomous forward-paper candidate

The application now has a persistent prospective account for the selected 20%
long/cash candidate. It collects genuine completed Binance daily history and
current bid/ask quotes, makes at most one decision per UTC week, simulates
fractional fills with spread, fees and adverse execution, persists state in
SQLite, reconstructs deterministically after restart, and tracks doubled-cost
results. It has no broker-routing method.

The first genuine observation was recorded on 6 November 2026 at 03:20
Singapore time. It allocated 19.06% to BTC and 13.82% to ETH, retained $335.37
cash, and marked the $500 account at $499.75 after $0.25 modeled initial costs.
This single observation is infrastructure evidence, not performance evidence.
Read the [forward-paper report](research/defensive_forward/REPORT.md).

```sh
python -m scripts.start_defensive_forward --db runtime/trader.db --capital 500
python -m trader serve
```

Keep the application process running to collect future observations. The first
12 decision weeks are a minimum evidence period; passing them still cannot
automatically activate broker execution.

On Windows, the included launcher activates the frozen account and starts the
dashboard/scheduler in one step after the virtual environment is installed:

```powershell
.\scripts\start_12_week_forward.ps1
```

On Linux or macOS, run `./scripts/start_12_week_forward.sh`. Leave the process
running. Closing it pauses data collection without erasing the account; running
the launcher again resumes the same SQLite record. The dashboard **Stop** button
marks the account inactive and therefore requires an explicit Start to resume.
Inspect it without changing state with:

```sh
python -m scripts.forward_status --db runtime/trader.db
```

If started on 6 November 2026 Singapore time and kept running, the first 12
complete Monday-to-Sunday evidence weeks end on 31 January 2027; the earliest
12-week assessment is therefore around 1 February 2027. Missed or invalid
observations are retained as operating evidence and are not silently backfilled
as contemporaneous quotes.

A laptop is not the recommended 12-week host. The no-cost default is the
[scheduled GitHub Actions forward paper](GITHUB_ACTIONS_FORWARD.md): a runner
wakes daily, advances the credential-free account, persists SQLite to a public
state branch, and shuts down. No laptop or server remains powered. The
[Ubuntu systemd deployment](FORWARD_HOSTING.md) remains available when exact
host control is worth paying for.

The free workflow is active as of 7 November 2026. Its first authoritative run
persisted one genuine public-data observation with $500 cash, no trade, no
error and live-order capability disabled. A second same-day runner restored the
database and correctly kept the observation count at one. Inspect the current
[public paper status](https://github.com/akshayagg18/finrl-x-trader/blob/forward-paper-state/status.json).

### Predeclared ETF rotation challenger

A separate 16-configuration experiment was declared and committed before its
dedicated Yahoo snapshot was downloaded. Development (2018–2020) and validation
(2021–2023) selected `mom252_sma200_top2_vol15` before evaluation was opened.
It rotates monthly among SPY, QQQ, IWM, GLD and TLT, using SHY as the cash hurdle,
with the same 20% per-asset and 40% total caps.

The locked January 2024–30 October 2026 evaluation returned **22.55%** after
modeled costs with **-4.60%** maximum drawdown; doubled costs returned 21.57%.
Independent two-month resets from January 2022 were 17 profitable, 8 losing and
3 flat, averaging +0.64% or $3.22. A 40%-SPY comparator returned 26.06% with
-8.77% drawdown, while the equal ETF basket returned 20.85% with -5.72%
drawdown. The challenger therefore improves the diversified comparison and the
selected BTC/ETH candidate historically, but does not beat SPY's raw return.

Read [the locked report](research/etf_rotation_challenger/REPORT.md). The result
is retrospective and is displayed read-only in the dashboard. It cannot reset,
replace or route orders from the existing forward account. It warrants a
separate prospective comparison after operational quote handling is completed.

### Deeper long/cash research on both tracks

The next experiment stayed inside long-only holdings plus cash. Its protocol
was committed before evaluating 63 crypto ensemble configurations and 16 ETF
exposure profiles; both development/validation choices were committed before
the already-inspected diagnostic evaluation was opened.

- The selected crypto ensemble votes across 100/150/200-day trends and
  30/90/180-day momentum, uses the weekly BTC gate, retains 20% per-asset and
  40% total caps, and targets 40% annualized volatility. Its January 2024–October
  2026 diagnostic return was **+27.40%** with **-12.39%** drawdown, versus
  +5.04% and -18.54% for the frozen candidate. Four-times costs returned
  +23.48%; a one-day execution delay returned +20.14%. It lost 5.79% in the
  2026 calendar reset and still has a negative weekly confidence bound.
- The selected ETF extension kept 20% per-asset and 40% total caps while moving
  the volatility target from 15% to 20%. It returned **+25.20%** with **-5.35%**
  drawdown, versus +22.55% and -4.60% for the first ETF candidate. Four-times
  costs returned +22.21%; a three-session delay returned +23.23%; every
  single-ETF removal remained profitable. It still trailed 40%-SPY/cash's
  +26.06% raw return, while SPY drawdown was worse at -8.77%.

Both qualify only as separate prospective challengers. The existing BTC/ETH
forward record stays frozen and unchanged. Read the
[full long/cash deepening report](research/long_cash_deepening/REPORT.md).

## Cost-aware profitability research (November 2026)

The repository now includes a leakage-controlled XGBoost workflow for expected-return forecasting, cost-aware execution, regime/sizing ablations, cost stress, and a constrained long-only opening-range-breakout comparison. It uses the existing frozen market snapshots and never routes orders to a broker.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-intraday.txt
.venv\Scripts\python.exe -m scripts.research_profitability
.venv\Scripts\python.exe -m pytest tests/test_profitability.py -q
```

Results are shown in Research & backtests and retained under `research/profitability/`. That specific ML experiment found **NO QUALIFIED PROFITABLE STRATEGY**. The final selected XGBoost candidate placed zero trades; the paper-style mechanism lost 5.55%; the limited equity ORB pilot lost 1.18%. See `research/PROFITABILITY_RESEARCH_RESULTS.md` and `research/FINAL_STRATEGY_RECOMMENDATION.md`. These are historical simulations, not paper-account or real-money returns.

Working local application built alongside the actual FinRL-X upstream source at commit `4409abe925c904e570be78ebfb5e77ac3491dff8`. The original README, Docker files and environment example are preserved as `*.upstream.*` files. Upstream algorithms in `src/` are unchanged.

**Usable now:** $500 persistent local simulation, genuine historical data, Adaptive Rotation and Equal Weight, cost-aware backtests, out-of-sample reporting, strategy comparison, rolling ML research training, SQLite audit trail, configurable risk/capital sizing, calendar scheduler, professional local dashboard, broker SDK adapters. No credentials or paid AI subscription required.

**Status:** This is a functional local trading application, not a verified production brokerage deployment. See [VERIFICATION.md](VERIFICATION.md) for exact tests and unfinished features. In particular, DRL deployment and the published ensemble are unavailable, ML is research-only, and actual broker behavior awaits external verification. The published +19.76% is **not** an installation result.

## Historical configuration experiment

The [completed configuration search](research/configuration_search_2026-11-03/REPORT.md) compares 61 configurations across 136 real-data backtests. The training/validation-selected candidate lost 2.82% in the untouched October 2025–October 2026 test, versus +1.67% for existing defaults and +13.89% for SPY. It is **not recommended for deployment** on this evidence. Deployed settings remain unchanged. The report includes exact settings, all results, frozen data, cost stresses and an interactive offline chart.

Recompute without credentials or network: `python -m scripts.search_configurations --output runtime/reproduced-search`.

## Start locally (Linux / macOS)

Python 3.12 recommended. `requirements-tested.txt` records the complete tested environment (including development tools) for reproducibility. Run from this repository's root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-app.txt
python -m trader init
python -m trader serve
```

Open **http://127.0.0.1:8765**. The backend, dashboard and persistent scheduler run in one process. No separate frontend build or scheduler service is needed. Use one Uvicorn worker. Automation is initially stopped; live execution is disabled. An `.env` file is optional; `.env.example` has blank broker credentials.

On Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-app.txt
python -m trader init
python -m trader serve
```

If script execution is restricted, invoke `.\.venv\Scripts\python.exe` directly. The OS process owns the scheduler; keep it running for automation. Ctrl+C stops the service, but does not cancel orders already submitted to an external broker.

## First real-data offline run

1. Open Settings → Broker. Local + simulation are the defaults.
2. Capital defaults to $500. Risk settings, presets and simulated execution costs are editable and persisted.
3. Return to Portfolio. Keep replay execution date **2025-01-06**, then preview or execute a simulated cycle.
4. Inspect positions, fills and decision audit. Later replay dates must advance chronologically. Repeating an already completed date returns its saved cycle without duplicating orders.
5. Research & backtests → run the default 2025-01-02 through 2025-10-07 backtest. Save a second run to compare settings under the same dates/capital.

Equivalent commands:

```sh
python -m trader simulate --date 2025-01-06 --dry-run
python -m trader simulate --date 2025-01-06
python -m trader backtest --start 2025-01-02 --end 2025-10-07 --oos-start 2025-07-01
python -m trader status
```

The bundled snapshot spans 2020-12-01 through 2025-10-07, with 130 sessions required before a test starts. Stock/SPY/QQQ bars come from the upstream archived database. SPX/VIX came from Yahoo's historical chart service. Every price file has a provenance manifest and SHA-256. `sample_data/fundamentals.csv.gz` is the upstream fundamental CSV compressed without changing its records. It contains historical vendor data, not a certified vintage dataset.

Historical OHLC prices are normalized using vendor adjusted-close factors for consistent split/dividend research units. These units differ from actual historical raw share quantities and approximate reinvestment through adjusted prices. **They are never used as live execution quotes.** External trading requires separately fetched, fresh broker quotes and instrument eligibility. Corporate-action continuity in a live bot ledger is not automated: unexplained share/cash changes fail reconciliation and require investigation.

## Docker Compose

```sh
docker compose up --build -d
docker compose logs -f console
docker compose stop
docker compose start
```

Same URL: **http://127.0.0.1:8765**. The named `trader-state` volume retains the SQLite database, market cache, models and backups. Do not run `docker compose down -v` unless you intend to delete all state. Containers run as an unprivileged user with a read-only application filesystem. Only the runtime volume and `/tmp` are writable.

If building behind a corporate TLS proxy, pass a combined CA bundle as a BuildKit `proxy_ca` secret; do not disable certificate verification. Managed-environment verification uses `docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -t finrl-console:local .`.

## Automation and live activation

For current-day operation, choose Data → Yahoo and download current bars. Cache mode deliberately rejects stale data for current cycles; historical replay remains available offline. Use broker paper trading before connecting live. Settings → Broker connects the adapter and identifies the account; **dedicated account is required**. The broker identity must match the selected ID. The bot never treats the whole broker cash balance as its allocation.

- Start: schedule monitoring and one rebalance per configured strategy period during NYSE sessions.
- Pause: stop new allocations; continue reconciliation and protective stop reductions. Existing open orders remain active until filled/canceled.
- Stop: stop scheduler actions; open orders remain at the broker.
- Kill: immediately block subsequent submissions; already in-flight orders may still fill. Cancel open orders separately.
- Emergency liquidation: explicitly requested market reductions of owned positions only, constrained by order size/daily counts. May require multiple cycles and can fail. Cancel pending orders and reset kill before requesting it.

The next operation is calendar-aware, including U.S. holidays, DST and early closes. State resumes after restart. An uncertain order submission leaves a durable intent; the bot reconciles by client ID and **never blindly retries it**. An interrupted cycle remains halted for operator review even when the broker confirms fills. Restore operations revoke activation and set kill.

Live requires selecting live mode, using separate live credentials, and typing `ENABLE LIVE TRADING` once. Thereafter no per-order approval is required. Broker/account/capital/strategy changes revoke activation and stop automation. Loss-trigger halts latch until explicitly acknowledged. Risk defaults and presets are design assumptions, not optimized protection or guaranteed maximum loss.

## Architecture

`trader/strategies.py` calls actual upstream weight generators. Central `risk.py` validates weights and order sizing. `ledger.py` transactionally applies cumulative fills to bot ownership. `brokers.py` exposes the common adapter, official Alpaca SDK and IBKR Gateway adapter. `service.py` coordinates reconciliation, orders, settings and controls. `backtest.py` evaluates t-1 signals at the next session open with the same sizing/risk/simulated fill modules. `scheduler.py` implements NYSE-aware persistent scheduling. `api.py` serves a FastAPI API plus a dependency-free browser UI with locally served Plotly charts. SQLite WAL contains accounts, positions, cycles, order intents, fills, equity, versioned configuration, models, research and audit events.

The upstream `bt` backtester remains intact, but its large-capital/whole-share path is not used for the operational simulator. Historical research and local/broker-paper/live histories have separate scopes. Capital deposits/withdrawals are flows, excluded from time-weighted returns. Intraday marks are aggregated to daily observations for statistics. Short series display insufficient-data labels.

## Tests

```sh
pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q
```

Browser tests launch a temporary local server, isolated SQLite database and real Chromium. No actual broker is contacted by automated tests. See [VERIFICATION.md](VERIFICATION.md).

## State, logs, backups and restore

Default state: `runtime/trader.db` plus `runtime/market/`, `runtime/models/` and `runtime/backups/`. Set `TRADER_DB` to change it. SQLite initializes automatically; migrations reject newer schema versions. Settings are stored as validated versions in SQLite, not silently overridden by `.env`. API credentials live only in backend environment variables. Use disk encryption and filesystem access controls for private trade history.

Audit logs: dashboard → Decision audit, persisted in `events`; process/HTTP logs go to stdout (Compose: `docker compose logs console`). CSV exports are available for orders, equity, events and research. Historical result fills/equity export separately.

```sh
python -m trader backup /safe/location/trader-backup.db
# Stop service first; restore to a NEW path (never overwrite a running database).
python -m trader --db runtime/restored.db restore /safe/location/trader-backup.db
# Set TRADER_DB=runtime/restored.db before restarting.
```

Copy market cache and model artifacts separately alongside the database backup. In Docker, use the Settings backup button, then `docker compose cp console:/app/runtime/backups ./backups`. A database backup is transactionally consistent; copying an active `.db` without its WAL is not a substitute.

Local access is intentional. Host validation and same-origin/custom-header checks restrict browser mutations; secrets are never returned to the browser. There is no remote-user authentication layer. Do not expose the port publicly. For remote access use an SSH tunnel to the loopback port or add a private authenticated TLS reverse proxy with an explicit host policy change. No withdrawal or transfer API is implemented.

Additional references: [CONFIGURATION.md](CONFIGURATION.md), [BROKER_SETUP.md](BROKER_SETUP.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), and [README.upstream.md](README.upstream.md).

## Intraday research extension (partial implementation)

Install `pip install -r requirements-intraday.txt`, then launch the same console with `python -m trader serve` at http://127.0.0.1:8765. Research & backtests → Intraday lab runs actual NautilusTrader cash-account backtests on bundled 15-minute bars with $500 default capital. Settings and research results persist in SQLite; existing deployed settings are separate. No credentials are needed.

Run `python -m scripts.benchmark_intraday` and `python -m scripts.report_intraday` to reproduce the preliminary comparison. Saved development trials are resumed; use a separate copy/remove only generated results when changing experiment code. Read [actual results](research/BACKTEST_RESULTS.md) and [limitations](research/FINAL_RECOMMENDATION.md).

This extension is historical research, **not yet autonomous intraday paper/live trading**. The original swing-trading scheduler and adapters are unchanged. Five-minute/ML comparisons, continuous intraday simulation, cross-market account ownership and Singapore exchange execution remain unfinished.

## ML and continuous replay update

Install/update `pip install -r requirements-intraday.txt`, then `python -m trader serve`. At **http://127.0.0.1:8765**, open Research & backtests → Intraday lab.

- Train random forest or gradient-boosted models with a cutoff before your evaluation dates; select any saved model version to compare or roll back. Five- and fifteen-minute BTC/ETH datasets are bundled.
- Configure the $500 virtual budget, risk and execution costs; run a backtest or create a continuous local simulation session. Click Start to advance 16 historical bars every scheduler tick. Pause blocks entries while exits/stops continue. Stop freezes replay. Liquidate sells at the next replay bar.
- Sessions and fills persist in the existing SQLite database. Restarting reconstructs the Nautilus execution state and resumes the saved cursor without duplicate fills or forced cycle-end sales. Datasets and session configurations are frozen for reproducibility.
- This is accelerated **historical local simulation**, not broker paper trading or a streaming live-feed simulator. Existing swing-trading accounts stay separate.

Reproduce the ML study with `python -m scripts.benchmark_ml`, then `python -m scripts.report_ml`. [Actual ML results](research/intraday_ml/REPORT.md) show **no qualified live strategy**. Model artifacts live in `runtime/intraday_models/` and are excluded from Git; training reproduces them. Back up that directory, the market snapshots and the SQLite database together. Restore the same package versions recorded in `research/intraday_ml/environment.json` when reproducing results.

The OKX CCXT transport is implemented and mock-tested, but is not wired into intraday live scheduling. Regional eligibility and private-account verification, fractional equity execution, and full multi-market live capital/risk routing remain outstanding. Earlier sections describing ML/replay as unfinished are superseded by this update; these external execution limitations remain.

## Growth research and forward observation

The [growth evaluation](research/growth/REPORT.md) implements longer 4/24/72-hour forecasts, net-return labels, chronological residual calibration, sparse-sample rejection, a continuous BTC/ETH portfolio and weekly statistics. Run `python -m scripts.evaluate_growth` to reproduce it. All 288 candidate trials are retained. The resulting policy lost 3.35%; **no strategy qualified**.

Research & backtests → Growth research shows comparison charts and the qualification reasons. Forward local simulation collects **new public quotes hourly** and persists them separately from historical replay. Configure $500 and click Start observation; the account stays cash while no model is qualified. Stop suspends observation; the global kill switch also stops it. The initial verification recorded genuine quotes with no trades. Twelve weeks of forward evidence remain a real elapsed-time requirement.

Monthly research produces model versions; a forward candidate must have passed historical qualification and remain freshly validated. Missing/overdue validation or stale data stops simulation. No automatic promotion to real-money trading is implemented or implied.

## Locked long-history regime experiment

The [regime/ML report](research/strategy_v2/REPORT.md) evaluates a lower-turnover
BTC/ETH hypothesis on public hourly history from August 2017 through October
2026. Daily trend, completed-four-hour momentum, and a volatility regime produce
the base signal; random-forest and histogram-boosted models can filter entries.
Features are lagged, labels must mature before training cutoffs, 2022 is the
selection year, and 2023–October 2026 is opened only after selection is locked.
The [two-month hold breakdown](research/strategy_v2/HOLD_2MONTH_REPORT.md)
separately reports every complete January 2022–October 2026 reset window.

No candidate qualified. The rule lost 1.65% in 2022 and 6.45% in the diagnostic
final evaluation. The least-bad validation ML filter lost 1.35% in 2022; it later
lost 1.77% at base modeled costs and 6.08% with doubled costs, with a negative
weekly confidence bound despite 197 completed exits. It is therefore
research evidence, not a deployed or profitable model. Research & backtests now
shows the result and both historical/live qualification states.

Reproduce the frozen experiment with:

```sh
python -m scripts.download_long_history
python -m scripts.evaluate_regime_strategy
python -m scripts.report_regime_strategy
```

The download is from Binance's public archive for history length. It cannot
verify OKX Singapore fees, eligibility, spreads, or fills. Runtime model binaries
are excluded from Git and recreated by the evaluation. Live trading remains
disabled and the existing forward simulator remains cash because no strategy
passed its historical gate.
