# FinRL-X Trader — handoff and current state

## Latest update — defensive trend and risk frontier, 6 November 2026

A fixed 81-configuration search found one validation-ranked rule that remained
positive in every chronological partition and under doubled modeled costs while
keeping evaluation drawdown just inside the user's 10% tolerance. It checks a
100-day BTC trend and 90-day momentum each Monday, allocates no more than 10%
to BTC and 10% to ETH, volatility-scales positions, and holds at least 80% cash.

- Development 2019–2021: +6.98%, -1.23% maximum drawdown.
- Validation 2022–2023: +4.73%, -3.28% maximum drawdown.
- Evaluation 2024–October 2026: +2.84%, -9.67% maximum drawdown.
- Doubled-cost evaluation: +2.31%, -9.86% maximum drawdown.
- Independent two-month windows from January 2022: 10 positive, 9 negative, 10
  flat; average +0.20% ($0.98), average maximum drawdown -1.23%.

This is a **historically profitable candidate, not a deployment-qualified or
consistently weekly-profitable strategy**. A same-risk passive comparison earned
more (+8.20%) but had -22.51% drawdown. The candidate's weekly bootstrap lower
bound is negative, and the final interval was viewed during exploratory work.
It needs a newly elapsed 12-week paper observation and target-account execution
evidence. Code and locked artifacts are in `trader/growth/defensive.py`,
`scripts/evaluate_defensive_trend.py`, and `research/defensive_trend/`.

The follow-up risk frontier also tested 20% and 50% drawdown budgets. The 20%
tier returned +5.04% in the 2024–October 2026 diagnostic period with -18.54%
drawdown; the 50% tier returned +7.50% with -40.87% drawdown. Doubled-cost
returns were +3.97% and +4.79%. The 50% tier is not preferred because 22.33
percentage points of additional drawdown produced only 2.46 percentage points
of extra return. Both remain diagnostic and deployment-blocked. See
`research/drawdown_frontier/REPORT.md`.

Three derivative/hedge tracks were then evaluated to the same research depth.
The BTC short overlay and BTC/ETH market-neutral strategy passed historical
selection but lost money in the 2024–October 2026 diagnostic evaluation at all
risk tiers. Synthetic protective puts slightly reduced drawdown but reduced
returns more: at the 10% tier, +1.94% with -9.50% drawdown versus +2.84% and
-9.67% for long/cash; at higher tiers the put strategy failed cost stress.
Long/cash therefore remains the preferred historical track at every tier. No
track is deployment qualified. Read `research/hedge_comparison/REPORT.md` and
the three track reports before changing the research direction.

The selected next action is implemented: a persistent prospective forward-
paper account for the **20% long/cash tier**. It recorded its first genuine
Binance public observation on 6 November 2026 at 03:20 Singapore time,
allocated 19.06% BTC and 13.82% ETH, retained $335.37 cash, and marked $499.75
after $0.25 modeled initial transaction cost. The local runtime account remains
active and will resume when the application scheduler runs. Its private SQLite
state is excluded from Git; the public verification snapshot is in
`research/defensive_forward/initial_observation.json`. One observation is not a
track record. Broker promotion remains technically impossible from this module.

## 0. Cost-aware profitability research update — 3 November 2026

A new expected-return XGBoost workflow, paper-mechanism replication, regime/sizing ablations, raw signal diagnostics, and long-only equity ORB pilot were added without changing broker routing or live controls.

- Six crypto interval/horizon configurations plus four selected-strategy walk-forward folds were evaluated under $500 cash-account constraints.
- The development selector fell back to hourly/one-hour forecasting but explicitly remained unqualified because its +3.22% came from one trade.
- Final August-October strategy holdout: 0.00%, zero trades; 900 positive forecasts but none above the 0.4827% cost-plus-uncertainty hurdle.
- Paper-style hourly mechanism: -5.55%, four trades, -8.22% drawdown, risk halt triggered.
- Limited 15-minute AAPL/SPY/QQQ long-only ORB pilot: -1.18%, 25 trades; not a reproduction of the broad-universe paper.
- Final comparator: 24-hour momentum +2.63% but -8.19% drawdown and materially below true 60%-deployed BTC buy-and-hold at +13.75%; ETH buy-and-hold returned +12.42%, while mean reversion lost 4.83%.
- Conclusion remains **NO QUALIFIED PROFITABLE STRATEGY FOUND**. Live trading remains disabled.

Reproduce with `.venv\Scripts\python.exe -m scripts.research_profitability`. Read `research/STRATEGY_FAILURE_ANALYSIS.md`, `research/PAPER_REPLICATION.md`, `research/STRATEGY_EXPERIMENTS.md`, `research/PROFITABILITY_RESEARCH_RESULTS.md`, and `research/FINAL_STRATEGY_RECOMMENDATION.md`.

Verification for this update: 6 focused tests and 42 compatible non-native tests passed. The full suite was attempted, but this Windows host blocked `pyarrow.lib` under Application Control while collecting five Nautilus/API/UI modules; do not misstate that environmental collection failure as a complete pass.

**Updated:** 5 November 2026, Asia/Singapore.

**Code baseline reviewed:** `c5a28b7`.

**Repository:** https://github.com/akshayagg18/finrl-x-trader — branch `main`.

**Upstream:** https://github.com/AI4Finance-Foundation/FinRL-Trading — foundation commit `4409abe925c904e570be78ebfb5e77ac3491dff8`.

## 1. Read this first

This is a working self-hosted research and simulation application with an existing FinRL-X swing-trading console, additional NautilusTrader intraday research, ML experiments, persistent historical replay, a growth/weekly-consistency workflow, and a locked long-history regime experiment.

**There is no deployment-qualified profitable strategy. Do not enable real trading based on the existing results.** The defensive rule is positive retrospectively but fails the weekly confidence and prospective-evidence gates. Earlier regime and ML candidates lost money or failed selection. Software functionality does not establish a durable investment edge.

- Latest recorded complete regression run: **102 passed**, 5,066 dependency deprecation warnings, 63.91 seconds. Evidence: [verification log](research/defensive_forward/verification_tests.txt).
- No real-money orders or actual brokerage paper-account executions were submitted during development.
- No brokerage credentials were supplied. The application starts without them.
- Live trading defaults off. The original swing console has an explicit live activation mechanism; it is not a verified production deployment.
- Intraday/growth research and simulation do **not** automatically route to real brokers. The CCXT OKX transport is not wired into autonomous intraday execution.
- The earlier model-driven forward check recorded one genuine cash-only
  observation and was stopped. The newly selected defensive account is a
  separate continuous record: its first genuine observation placed two
  simulated fills and it remains enabled in the private local database. It is
  still only the first observation of a minimum 12-week forward trial.
- Latest scope is **long-term net growth with more profitable weeks**, allowing overnight/multiday holdings and accepting losing weeks. It is not a promise of weekly income.

This file consolidates the current state. README and VERIFICATION contain chronological updates; earlier claims that all ML, replay, settlement, or forward observation are absent are partially superseded. Do not interpret old completion checklists as current implementation status.

## 2. User intent and decisions already made

The original request was a complete autonomous, self-hosted application based on actual FinRL-X, initially using approximately **US$500**, with real-data backtests, usable local simulation, configurable allocation/risk, persistence, a dashboard, and later broker connection. The user subsequently requested crypto/equity intraday comparison, ML models, better profitability research, and GitHub access for use on a PC.

Persist these preferences:

- Make reasonable engineering decisions independently; do not repeatedly request permission between ordinary implementation stages.
- Do not request API keys during development. Implement/test everything feasible without them.
- Preserve working upstream/console functionality. Reuse maintained engines instead of replacing everything.
- No fabricated prices, trades, profits, credentials, or operational broker status.
- After eventual explicit live activation, the intended product is autonomous within configured limits, without per-order approvals. This does **not** authorize development-time real orders.
- Keep historical research, accelerated replay, forward local simulation, broker paper and live performance separate.
- Do not spend unrelated account cash or sell manually owned assets. The existing external-account design requires a dedicated account.
- Core functionality must not require paid LLM services.
- User accepted **growth over time**, **holding for several days**, and a **$50 / 10% peak-to-trough tolerance on $500**. The latter is a risk budget, not an enforceable guarantee through gaps.
- GitHub pushes to the supplied repository have been authorized and performed throughout development. Never commit runtime databases, keys or private account history.

## 3. How the project got here

| Commit | Work added | Outcome |
|---|---|---|
| `2000aac` | Original FastAPI console, FinRL-X bridge, local ledger/simulation, risk, backtests, broker adapters, scheduler and UI | Working credential-free local application; external production gaps documented |
| `051bd1b` | 61-configuration daily-strategy search, 136 simulations, frozen data and offline report | Selected candidate failed to outperform on later evaluation |
| `ff5ca1e` | Nautilus intraday research, public crypto/equity data, dashboard integration | 90 scenarios; no qualified strategy |
| `441fda2` | RF/boosted ML, five-minute data, walk-forward study, persistent continuous historical replay, settlement and CCXT transport | 116 ML evaluations; no reliable net edge |
| `b365174` | Longer-horizon growth models, continuous two-asset portfolio, stricter validation, weekly statistics and qualification-gated forward observation | 288 candidate trials plus six portfolio scenarios; no qualified strategy |
| `c5a28b7` | Frozen 2017–2026 hourly archive, low-turnover regime rules, optional ML entry filter, locked evaluation and dashboard evidence | Rule and all ML filters failed 2022 selection; no qualified strategy |

Upstream source lives in `src/`. The original README, Docker and environment material was preserved in upstream-named files. The upstream published **19.76%** result is not a result reproduced by this installation; exact ensemble/artifact reproduction remains unavailable.

## 4. Current capability matrix

| Capability | Current state | Important boundary |
|---|---|---|
| FinRL-X Adaptive Rotation / Equal Weight | Working through upstream weight generators | Daily/weekly portfolio strategies, separate from new ML research |
| Original $500 local broker | Working, persistent positions/orders/cash | Virtual funds; adjusted research prices never become live quotes |
| Historical backtesting | Working with real stored data and modeled costs | Data revisions, static universe and execution assumptions remain |
| Upstream rolling stock-selection ML | Research training/artifacts available | Fundamentals are not certified point-in-time; external deployment unfinished |
| Upstream DRL / published ensemble | Not operational | Requires integration/artifacts; not just credentials |
| Intraday 5/15-minute research | Working in NautilusTrader | Crypto spot, whole-share equity research; full fills assumed |
| Intraday RF / boosted models | Working training, versions and evaluation | No model qualified; previous October data is no longer pristine holdout |
| Continuous historical replay | Working, scheduler-driven, restartable | Accelerated historical time; not a live market feed or broker account |
| Growth hourly research | Working, 4/24/72-hour targets | One continuous BTC/ETH virtual account, stricter selection |
| Long-history regime/ML research | Working, reproducible download and locked evaluation | Diagnostic only; failed selection and stress gates; not connected to execution |
| Forward local observation/simulation | Working public-quote capture and persisted modeled execution path | Defaults to cash; model use blocked by qualification; hourly risk monitoring |
| Alpaca | Official SDK adapter implemented and mock-tested | Real paper/live credentials, permissions, fees and execution require verification |
| IBKR | Gateway/TWS adapter implemented and mock-tested | External session/entitlements needed; whole shares; verification flag defaults false |
| OKX | Public data works; CCXT private transport methods implemented/mock-tested | Regional eligibility/default host unverified; not wired into intraday orchestration |
| Dashboard | FastAPI serves plain JavaScript/HTML/CSS and local Plotly | No React build; local-only; no remote-user authentication layer |
| Production autonomous intraday brokerage | **Unfinished** | External ownership, risk routing, reconciliation and operational verification still required |
| Proven profitable weekly trading | **Not established** | Do not weaken research gates to manufacture a winner |

## 5. Architecture and where to look

### Original console

- [API](trader/api.py): FastAPI application, host/origin checks, mutation intent header, static frontend and optional research routers.
- [Service](trader/service.py), [ledger](trader/ledger.py), [brokers](trader/brokers.py): broker binding, account ownership, order intents, reconciliation, cumulative fills and local simulation.
- [Risk](trader/risk.py): weight/order constraints and the portfolio-loss helper shared with newer components.
- [Strategies](trader/strategies.py): upstream Adaptive Rotation / Equal Weight bridge and capability catalog.
- [Backtest](trader/backtest.py): prior completed-bar signals, following-session execution and daily valuation.
- [Database](trader/db.py): SQLite WAL, schema initialization, settings history, state and audit events.
- [Scheduler](trader/scheduler.py): **one process-level scheduler**, roughly ten-second loop; forward/growth and intraday hooks precede the original NYSE-aware swing logic.
- [Frontend](trader/static/app.js), [markup](trader/static/index.html), [styles](trader/static/style.css): portfolio, settings, research, models, replay and forward controls.

### Intraday subsystem

- [Engine](trader/intraday/engine.py): real Nautilus cash-account execution against modeled quotes derived from historical opens; precision/minimums, costs, stops and T+1 proceeds tracking.
- [ML](trader/intraday/ml.py): lagged features, matured-label training cutoffs, random forest/histogram gradient boosting, local hash-verified model artifacts.
- [Replay](trader/intraday/replay.py): immutable virtual sessions, deterministic engine reconstruction, process locking, atomic checkpoints and stable fill identifiers. Positions remain open between cycles.
- [Exchange](trader/intraday/exchange.py): guarded OKX spot transport via CCXT, separate demo/live credentials, uncertain-submission handling, no transfer/withdrawal methods.
- [Analytics](trader/intraday/analytics.py), [API](trader/intraday/api.py): fill-based analytics, model management and session endpoints.

### Growth / weekly-consistency subsystem — current research focus

- [Config](trader/growth/config.py): accepted conservative budget/risk limits.
- [Models](trader/growth/models.py): complete-hour aggregation, net-return labels and rolling training.
- [Portfolio](trader/growth/portfolio.py): one Nautilus cash account across BTC/ETH; continuous positions, allocation/risk limits, cost attribution and shared portfolio loss checks.
- [Weekly statistics](trader/growth/weekly.py): Singapore Monday-start weeks, partial-boundary exclusion, four-week block bootstrap and qualification reasons.
- [Forward](trader/growth/forward.py): fresh public bid/ask observations, hourly deduplication, persistent reconstructed local execution, freeze-after-first-observation financial settings, gated version promotion and fail-closed behavior.
- [API](trader/growth/api.py): research results and forward configure/status/start/stop/model-promotion endpoints.

These subsystems share infrastructure but are **not one completed cross-market external-account execution engine**. Local virtual allocations are isolated; shared real-account ownership routing is still a separate engineering task.

## 6. Data, artifacts and state

| Location | Contents | Included in Git? |
|---|---|---|
| `sample_data/` | Original daily snapshots and compressed fundamentals; source/hash manifests | Yes |
| `research/configuration_search_2026-11-03/` | First configuration search, later daily snapshot and offline chart | Yes |
| `research/intraday/data/` | BTC/ETH 5m/15m CSVs, AAPL/SPY/QQQ 15m CSVs, provenance/instrument metadata | Yes |
| `research/intraday/results/` | Initial intraday protocol, trials, fills/equity and comparisons | Yes |
| `research/intraday_ml/` | Locked ML selections, compressed tests, analytics, model manifests and environment versions | Yes |
| `research/growth/` | Current protocol, 288 trials, schedule, versions, six scenario files, weekly CSVs, verification and genuine forward observation | Yes |
| `runtime/trader.db` | Default local application state | **No** |
| `runtime/intraday_models/`, `runtime/growth_models/` | Locally trained joblib files and model metadata | **No** |
| Other `runtime/` paths | Market caches, test databases, backups, source downloads and research state | **No** |

Crypto coverage: **2024-11-01–2026-10-31**, two years. Each 15m series has 70,080 bars; each 5m series has 210,240 bars. Growth derives 17,520 complete hourly bars per asset from the 15m snapshots. Equity intraday coverage is only about **60 trading sessions**, August–November 2026; this is inadequate for a strong long-term equity ML claim.

Models are **not downloaded by cloning Git**. Recreate them through the documented training/benchmark commands. Model IDs, metadata, data hashes and results are retained, but a manifest alone is not a trained estimator. Load only locally generated trusted joblib files; hashes do not make arbitrary pickle files safe.

SQLite separation:

- Original account/order/equity/cycle tables plus versioned settings, research and events.
- Intraday session/checkpoint/fill tables: `intraday_sessions`, `intraday_cycles`, `intraday_fills`; research configuration/history also uses separate state keys.
- Growth forward tables: `growth_forward`, `growth_observations`, `growth_fills`.
- Research additions use additive table initialization; they do not replace the original ledger.

Never merge these histories into one performance curve. A newly cloned repo has no privately persisted account state. One virtual account's $500 is not the balance of another virtual or brokerage account.

## 7. Actual results — do not claim more than these show

### Locked long-history regime/ML experiment (5 November 2026)

- BTCUSDT and ETHUSDT public Binance hourly archives span August 2017 through
  October 2026 with 80,581 raw rows each. The source is cross-venue research
  data, not OKX execution evidence.
- 2019–2021 is development, 2022 is validation, and 2023–October 2026 is the
  final diagnostic evaluation. The protocol and selection were hash-bound
  before the final interval.
- The diagnostic base rule returned +11.27% in development, −1.65% in
  validation, and −6.45% final. It failed selection.
- The forest/0.60 entry filter returned −1.35% in validation, then −1.77% final
  at base modeled costs and −6.08% at doubled costs. It has a negative lower
  confidence bound despite 197 exits. It failed selection and final
  qualification.
- A 60%-deployed BTC/ETH hold returned +136.93% with −52.35% drawdown. It is a
  risk benchmark, not an eligible trading policy.
- Across 29 independent two-month windows from January 2022 through October
  2026, the same hold benchmark averaged +2.11% ($10.57) with −14.40% average
  maximum drawdown; 15 windows gained and 14 lost. The worst window lost 33.76%.
- No model was deployed or promoted and no real or broker-paper order was sent.

| Experiment | Evidence | Outcome |
|---|---|---|
| Daily configuration search | 61 configurations, 136 runs; train 2022–23, validate 2024, later tests | Selected candidate −2.82% in 2025-10-08–2026-10-30; defaults +1.67%; SPY +13.89%; QQQ +14.51%. $1/order stress: −10.57% |
| Initial intraday | 90 scenarios; common October 2026 evaluation | BTC −14.19%, ETH −15.40%, AAPL −0.12%; SPY/QQQ stayed cash when whole shares were unaffordable |
| Intraday ML | 32 validation + 84 walk-forward scenarios | BTC 5m: −1.490% Jan–Feb, +0.293% Jul–Aug; BTC 15m: +0.032%, 0%; ETH variants negative/flat. All selected October models placed zero trades |
| Growth / weekly | 288 validation trials + six continuous portfolio scenarios | Selected −3.35%, ending $483.23, max DD −3.50%, 17 exits; same-trade gross −2.49%; doubled-cost net −4.13% |
| Forward observation | One genuine public quote observation, 3 Nov 2026 **17:51 Singapore time** | $500 cash, zero fills; verification account then stopped |

Latest growth evaluation is 2025-11-01–2026-10-31. It has **51 complete Singapore-time weeks**, with two partial boundary weeks excluded from consistency statistics: 0 profitable, 3 losing, 48 flat complete weeks. Worst complete week approximately −1.06%. Only one monthly candidate passed validation (BTC, boosted trees, 24-hour horizon, October deployment); that candidate subsequently lost money.

These figures have different dates, allocations, costs and rules. Do not compare them as identical accounts or aggregate independently reset folds into a continuous return. The growth account is continuous; earlier fold reports explicitly reset capital.

Source reports:

- [Daily configuration search](research/configuration_search_2026-11-03/REPORT.md)
- [Initial intraday](research/BACKTEST_RESULTS.md)
- [Intraday ML](research/intraday_ml/REPORT.md)
- [Current growth report](research/growth/REPORT.md)
- [Long-history regime/ML report](research/strategy_v2/REPORT.md)

**Previously inspected history is development evidence, not a fresh holdout.** October and other intervals have been examined repeatedly. Freeze a new protocol before collecting genuinely new observations. Zero-trade cash outcomes are not proven profitable strategies. Costs, full fills, depth, vendor revisions, survivorship and USDT/USD parity constrain interpretation.

## 8. Current agreed research/risk policy

| Parameter | Current default / requirement |
|---|---|
| Capital | $500 virtual allocation |
| Universe | BTC/ETH spot, no leverage or shorts |
| Holding horizons | 4 / 24 / 72 hours, overnight permitted |
| Maximum entry deployment / per asset | 60% / 30%; at most two assets |
| Cash reserve | 40% |
| Estimated initial stop risk | 0.5% equity per entry |
| Stops | Twice lagged daily-scaled volatility, bounded 1–15% |
| Daily loss control | Pause new entries at 2% |
| Peak drawdown control | Liquidate/halt at 8%; user tolerance is 10% |
| Training | Nine months, labels mature before cutoff |
| Validation | Three months: first for residual calibration, last two for ranking |
| Candidate selection | 2 model families × 3 horizons × 2 thresholds per asset; ≥20 exits, positive net in both scoring months, DD better than −10%; otherwise cash |
| Historical qualification | Positive net, positive doubled-cost result, DD below 10%, ≥52 complete weeks, ≥100 exits, positive lower 95% weekly block-bootstrap bound |
| Forward qualification | ≥12 complete weeks and ≥30 exits, plus profitability, drawdown, cost and uncertainty checks |

Exposure limits constrain order sizing; mark-to-market moves/gaps can exceed intended weights or loss triggers. Hold benchmarks intentionally bypass protective stops and therefore are **not eligible trading policies** simply because they are included in comparisons.

Monthly refits/selection are implemented in the historical evaluation script. This is not yet a complete unattended production model-training service. Forward models older than 31 days fail closed; fresh research validation/promotion must be supplied. No automatic real-money activation follows research qualification.

## 9. Run it on a new PC

### Recommended full setup: Python, repository root, one worker

```sh
git clone https://github.com/akshayagg18/finrl-x-trader.git
cd finrl-x-trader
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-intraday.txt
python -m trader init
python -m trader serve
```

`requirements-intraday.txt` includes the base app dependencies and pins NautilusTrader 1.231.0 / CCXT 4.5.91. Check recorded package versions in the research environment manifests when reproducing exact results; the base requirement ranges are not a fully frozen current environment.

Dashboard: **http://127.0.0.1:8765**. An `.env` is optional. No keys are needed for historical research or local simulation; forward public observations require internet connectivity.

Windows: create a Python 3.12 environment with `py -3.12 -m venv .venv`, then use `.venv\Scripts\python.exe` / `.venv\Scripts\pip.exe` or activate via PowerShell. The full Nautilus/CCXT stack has not been runtime-verified on Windows in this project; Linux/WSL2 is the safer fallback. Do not claim native Windows support from instructions alone.

### Check the main workflows

1. **Original simulation:** Portfolio → historical date `2025-01-06` → preview/execute; inspect actual simulated fills and positions.
2. **Intraday backtest:** Research & backtests → Intraday lab; choose cached dates, symbol and costs. Whole-share equity orders may legitimately be absent.
3. **ML:** train with a cutoff before the evaluation start; select the saved model version. Inference before training cutoff is rejected.
4. **Historical replay:** create an isolated session; Start advances 16 historical bars per scheduler tick. Pause stops entries but permits exits/stops; Stop suspends monitoring; liquidation acts at the next replay bar.
5. **Growth research:** review weekly comparison and rejection reasons.
6. **Forward observation:** configure a virtual account, then Start observation. It stays cash without a qualified model. It records a new hourly bucket, not replayed old market history. Stop suspends collection; global kill stops the simulator. Do not reset records to hide losses.

### Reproduce experiments

```sh
python -m scripts.search_configurations --output runtime/reproduced-search
python -m scripts.benchmark_intraday
python -m scripts.report_intraday
python -m scripts.benchmark_ml
python -m scripts.report_ml
python -m scripts.evaluate_growth
python -m scripts.download_long_history
python -m scripts.evaluate_regime_strategy
python -m scripts.report_regime_strategy
```

Some scripts resume cached results or overwrite tracked research outputs. Use a separate checkout/output where supported before changing algorithms, data or parameters; never silently mix results from different implementations. Download scripts can replace cached vendor history; preserve the frozen snapshots and manifests first. Run from the repository root because several modules use relative paths.

### Tests

```sh
pip install -r requirements-intraday.txt -r requirements-dev.txt
python -m playwright install chromium
python -m pytest tests -q
```

In the existing development workspace, browser binaries were stored separately:

```sh
PLAYWRIGHT_BROWSERS_PATH=/workspace/pw-browsers .venv/bin/pytest tests -q
```

That path is environment-specific; do not copy it onto an unrelated PC. The latest **recorded** full run is 82 passing tests in 60.70 seconds. Browser tests use isolated databases and actual Chromium. Broker calls in automated tests use mocks.

### Docker caveat discovered during this handoff

**The current Dockerfile covers the original console, not the complete latest stack.** It installs only `requirements-app.txt` and copies `src`, `trader` and `sample_data`; it does not install the intraday dependencies or copy `research/` and `scripts/`. Consequently, the latest research/growth functionality must not be advertised as fully available in that image.

Compose exists with loopback port mapping and persistent `trader-state`, but packaging the new capabilities and validating them inside a clean container is an outstanding task. For the full application, use the Python instructions above until that work is done. Preserve the non-root, read-only filesystem, loopback binding and persistent runtime volume when fixing Docker.

## 10. Operational state and safe handover

- Code defaults do not establish the current settings of every persisted database. Inspect the selected database's activation, kill, automation and session states before starting an existing deployment. This handoff did not audit the user's PC or certify an always-running service.
- Original automation, intraday session activation and growth forward activation are separate state flags. Original Portfolio controls are not interchangeable with all research controls; global kill is the shared stop gate.
- The process must stay running. One FastAPI/Uvicorn worker is expected. Forward collection and replay execute serially in the same scheduler thread; long reconstruction or network calls can delay subsequent tasks.
- Save SQLite using the existing backup mechanism, not by copying a running `.db` while ignoring its WAL. Copy model/data directories separately.

```sh
python -m trader backup /safe/location/trader-backup.db
# Stop services; restore into a NEW path, never over a running database:
python -m trader --db runtime/restored.db restore /safe/location/trader-backup.db
```

Restore sets kill and revokes original live activation. Explicitly inspect/reconcile all saved research/forward/session flags before restarting. The backup contains private state and must not be committed to Git.

Local-only host/origin/header checks are not remote authentication. Do not expose trading endpoints publicly. Keep credentials in backend environment variables. Use no withdrawal/transfer permission. `ALPACA_PAPER_*` and `ALPACA_LIVE_*` are separate; IBKR needs Gateway/TWS and entitlements; `OKX_DEMO_*` and `OKX_LIVE_*` are separate and `OKX_REGION_VERIFIED` defaults false.

The older model-driven verification account was stopped after one observation.
The selected defensive account began a separate prospective record on 6
November 2026 and remains enabled in the private local database. It collects
observations only while the application scheduler runs. The observation record
timestamps are authoritative; repository commits or elapsed wall-clock time
alone are not forward evidence.

## 11. Open work and priorities

### P0 — Make the handover/build and qualification boundaries reliable

1. **Complete Docker packaging for the full stack.** Install the proper requirements and copy required assets/scripts; define writable research-output locations compatible with the read-only image. Acceptance: clean build, credential-free launch, dashboard growth/intraday routes, real-data backtest and restart persistence inside Compose.
2. **Consolidate documentation and dependencies.** Retire contradictory historical status statements without destroying experiment history; create a tested full-stack lock/constraints file. Acceptance: a new checkout on the supported platform reproduces the documented setup.
3. **Bind promotion to exact evidence.** Current growth promotion checks a global `summary.selected.qualified` flag plus local model symbol/hash/age; inspect and strengthen binding to the exact approved model/config/data/protocol IDs before a future qualified flag could allow candidates. Do not manually edit JSON to make a model qualified. Acceptance: substituting a different otherwise-valid artifact is rejected.
4. **Audit qualification/coverage invariants.** Check missing-week continuity, model/data provenance, forecast-label timing, actual stop/fill behavior, fee assumptions and forward gaps. The existing tests and passing suite are evidence, not an independent production audit. Acceptance: adversarial tests fail closed and report insufficient data rather than invented continuity.

### P1 — Collect and evaluate new evidence without overfitting

5. Freeze a hypothesis, parameters, costs and acceptance criteria before new evaluation. Preserve all failed trials and do not rebrand previously inspected periods as untouched.
6. Run durable forward observation on an always-on local/private host. Track outages, data quality and operating time. Do not backfill old quotes as contemporaneous observations. Cash observation demonstrates infrastructure, not an executable alpha strategy.
7. Build an audited monthly training/validation job and exact-version promotion workflow. Keep the account continuous through promotion; retain old model artifacts for rollback. Fresh validation must precede activation. Stop on stale/unvalidated versions.
8. Improve data/cost evidence: actual eligible-account fees, spread/slippage measurements, funding/conversion costs, liquidity assumptions and sufficient intraday equity history. Equity data is currently too short for a robust comparable equity ML study.
9. Research another model/strategy only against a predeclared new protocol. More trees, more turnover or fewer safeguards do not create an edge. Reject models that cannot outperform costs robustly; retain cash if none qualifies.
10. Treat 2019–October 2026 as inspected for this regime family. Do not retune
    its thresholds on the final interval and relabel that period untouched. A
    next strategy needs a materially new predeclared hypothesis, target-venue
    cost evidence, and a later holdout or prospective observation.

### P2 — Finish external execution only after engineering and evidence gates

11. Integrate a single external-account orchestration layer for intraday/growth: dedicated account binding, bot-owned balances, settled cash, durable intents, account-level locking, partial fills, cancellation races, unknown submissions and reconciliation after restart. Existing transport methods do not supply this whole layer.
12. Verify Singapore account eligibility, regional OKX endpoint/demo support and fees. The CCXT adapter currently uses its default OKX host; a Singapore account may require different configuration. Public global data access is not proof of local trading eligibility.
13. Recheck broker rules when connecting. The prior research retrieved FINRA Notice 26-10, effective 4 June 2026 with phase-in through 20 October 2027; verify the particular broker's transition rather than assuming either the old $25,000 PDT rule or universal new behavior. T+1 cash restrictions remain relevant.
14. Complete fractional equity handling and broker-specific supported order types. Verify SDK contracts with actual paper credentials supplied later; do not fabricate successful paper fills.
15. Complete real net accounting: actual fees/commissions, delayed fee corrections, dividends, splits and statement reconciliation. Original Alpaca fill accounting does not yet attribute full account-activity fees; IBKR delayed commissions are not comprehensively revisited.
16. Add monitoring, alerting, independent watchdogs, long-duration recovery tests and execution-quality measurement. Existing single-thread reconstruction is useful for research but must be profiled before unattended external operation.

Acceptance for external readiness is a verified paper-account lifecycle with reconciliation under outages, partial fills and restarts—not merely passing mocked transport tests. Live activation must remain explicit and separate.

### Other known limitations to preserve honestly

- No demonstrated profitable weekly strategy; no completed required forward track record.
- DRL deployment and the published FinRL-X ensemble remain unavailable.
- Point-in-time fundamentals and historical membership are insufficient for certified upstream stock-selection deployment.
- Shared brokerage accounts, automatic external deposit attribution and automated corporate-action continuity are not production-complete.
- Stops are application-monitored, not guarantees. Growth forward sampling/protection is hourly; intrahour gaps are not modeled away.
- Candle-based research uses synthetic **execution quote assumptions derived from real prices**, not observed historical NBBO/depth. Actual public forward quotes are a separate evidence source.
- Replay/forward engine state is reconstructed from stored history. Runtime grows with history; no production throughput or high-availability claim has been established.
- Configured `fees_verified` metadata alone is not proof of an actual tariff. Treat fee verification as an external evidence requirement.
- The selected defensive forward path has two simulated opening fills but has
  not accumulated a qualifying trading record. Its initial cost-bearing mark
  is infrastructure evidence only.

## 12. Suggested first session for the next engineer/agent

1. Read this file, [current growth report](research/growth/REPORT.md), [verification](VERIFICATION.md), and the referenced implementation modules.
2. Check branch/status, installed dependencies and chosen database without disclosing credentials. Work from the repo root; preserve unrelated changes.
3. Reproduce the full test suite, then launch the complete Python application with a fresh temporary database. Inspect the mode labels and qualification reasons.
4. Address Docker/dependency reproducibility and exact-model qualification binding before expanding execution privileges.
5. Separate the research question (“is there a net edge?”) from execution engineering (“can an account operate correctly?”). Both must succeed for eventual real-money use.
6. Update this handoff with each completed milestone, actual test outputs, data period and commit. Do not replace failing results with unsupported success claims.

**Handoff status:** useful, tested research/simulation software; the preferred
20% long/cash candidate is running in isolated forward paper but remains
unqualified for broker deployment. The next step is uninterrupted prospective
evidence and operational hardening, while external autonomous brokerage still
requires implementation and credentialed verification.
