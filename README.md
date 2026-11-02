# FinRL-X self-hosted trading console

Working local application built alongside the actual FinRL-X upstream source at commit `4409abe925c904e570be78ebfb5e77ac3491dff8`. The original README, Docker files and environment example are preserved as `*.upstream.*` files. Upstream algorithms in `src/` are unchanged.

**Usable now:** $500 persistent local simulation, genuine historical data, Adaptive Rotation and Equal Weight, cost-aware backtests, out-of-sample reporting, strategy comparison, rolling ML research training, SQLite audit trail, configurable risk/capital sizing, calendar scheduler, professional local dashboard, broker SDK adapters. No credentials or paid AI subscription required.

**Status:** This is a functional local trading application, not a verified production brokerage deployment. See [VERIFICATION.md](VERIFICATION.md) for exact tests and unfinished features. In particular, DRL deployment and the published ensemble are unavailable, ML is research-only, and actual broker behavior awaits external verification. The published +19.76% is **not** an installation result.

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
