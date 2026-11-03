# Growth and weekly-consistency evaluation

**NO QUALIFIED STRATEGY.** The agreed changes are implemented; they did not create a profitable model. Live trading remains disabled. Forward local simulation defaults to cash because no policy passes the historical gates.

## Measured results

Continuous account, 2025-11-01 through 2026-10-31, $500 initial virtual capital, BTC/ETH spot. All returns are marked values, not realized final liquidation proceeds.

| Policy | Net return | Ending equity | Maximum drawdown | Completed exits |
|---|---:|---:|---:|---:|
| Selected monthly ML policy | −3.35% | $483.23 | −3.50% | 17 |
| Selected, 1.5× costs | −3.78% | $481.11 | −3.89% | 17 |
| Selected, 2× costs | −4.13% | $479.34 | −4.20% | 17 |
| Cash | 0.00% | $500.00 | 0.00% | 0 |
| 60%-deployed BTC/ETH hold | −21.31% | $393.45 | −32.63% | 0 |
| Simple trend with shared risk controls | −7.39% | $463.07 | −8.11% | 45 |

The selected policy's **same-trade gross return was −2.49%**. Recorded fees were $2.87 and estimated execution friction $1.43, with additional adverse closing-mark attribution. Gross holds the exact quantities/trades fixed and adds costs back; it is not a separate tradable strategy. Cost-stress runs independently execute the fixed decision schedule and can change sizing or halts.

Among **51 complete Singapore-time weeks**, the selected policy had **0 profitable, 3 losing and 48 flat weeks**. Two partial boundary weeks are displayed but excluded from consistency statistics. Worst complete week: −1.06%; longest complete-week losing streak: 3. Cash weeks are not successful trades. Bootstrap lower 95% mean-weekly bound was negative. The policy therefore fails profitability, sample-size and uncertainty gates.

## Predeclared experiment

Hourly features are aggregated from four genuine 15-minute bars; incomplete source hours are rejected. Universe stays BTC/ETH. Random forest and gradient boosting each predict 4/24/72-hour net returns, with two residual-confidence thresholds: 12 candidates per instrument.

Every monthly evaluation uses nine months of training followed by three months of validation. The first validation month calibrates forecast overestimation using only labels matured by that month's end. The remaining two months rank candidates. Qualification requires at least 20 validation exits, positive net return in each validation scoring month and drawdown better than −10%. The best qualifying family/horizon is refit on nine months ending at the evaluation boundary; all others remain cash. Calibration thresholds carry forward, without evaluation-period tuning.

There were **288 candidate validation trials** across 12 months and two assets, followed by six continuous-account scenarios. Only one candidate passed a monthly validation gate: BTC boosted trees, 24-hour horizon, for October 2026 (27 validation exits and +1.85% validation return). It lost money after deployment into the evaluation simulation. All candidates, including failures, are retained in [trials.csv](trials.csv).

Monthly model changes do not reset portfolio value, positions, cash or drawdown. No forced sale is inserted at a month boundary. Open holdings expire under their original holding horizon or stop. No strategy can recover its risk budget by resetting a fold.

## Risk and statistical gates

Maximum deployment 60%; each asset 30%; reserve 40%; at most two holdings. Entry size is capped by an estimated 0.5%-of-equity stop risk. Stops use twice lagged daily-scaled volatility, bounded at 1–15%; losses through gaps can exceed estimates. New entries pause at a 2% daily loss. Peak drawdown at 8% causes liquidation and a permanent simulation halt; it is a buffer against the user's 10% tolerance, not a guarantee. No leverage, shorts or loss-recovery sizing.

Hold is a passive benchmark using the same starting deployment/reserve and deliberately bypasses stop/halt logic. Its drawdown is not permitted for the selected trading policy. The simple trend benchmark obeys the risk controls.

Historical qualification requires positive net returns, positive doubled-cost results, drawdown below 10%, at least 52 complete weeks and 100 completed exits, and a positive lower 95% bound on mean weekly return from 2,000 circular four-week block-bootstrap samples. We do not loosen these gates because the sample falls short. A future forward candidate needs at least 12 complete weeks and 30 exits plus profitability/uncertainty/cost checks.

## Forward local simulation

The dashboard can create and start a separate virtual account collecting timestamped public OKX bid/ask observations hourly. It rejects stale, crossed or excessive-spread quotes and stops on transport/data failures. Observations, model identifiers, decisions, fills and account reconstruction are persisted atomically. Restarting or receiving the same hourly bucket does not duplicate fills. A public-data test recorded one genuine BTC/ETH observation and $500 cash with **zero fills**; see [forward_observation.json](forward_observation.json). That observation is not a performance claim. The verification account was stopped afterward.

No historical candidate passed, so model trading is blocked and forward cash observation is available. Private exchange credentials are neither loaded nor used. The simulator uses observed bid/ask plus assumed extra slippage and commission; actual execution would differ. Model versions must be locally hash-verified, match the instrument, predate decisions and be no older than 31 days. If fresh monthly validation is unavailable, simulation fails closed; it does not silently continue an obsolete model. Research selection must produce and approve a new validated version before resuming candidate trading. This is not automatic live brokerage execution.

## Reproduction and limitations

```sh
pip install -r requirements-intraday.txt
python -m scripts.evaluate_growth
python -m trader serve
```

Open http://127.0.0.1:8765 → Research & backtests → Growth research. [comparison.csv](comparison.csv), [weekly_returns.csv](weekly_returns.csv), the compressed scenario files and frozen protocol preserve the measured results. Runtime model binaries stay local and can be regenerated. Existing FinRL-X and previous intraday experiments remain separately accessible; their different dates/risk settings should not be read as directly comparable accounts.

These historical periods were already inspected in earlier research and are **development evidence**, not a pristine holdout. The final policy must be frozen before genuine future observations accumulate. No 12-week forward record can be manufactured today. Fees are estimates (10 bps plus 5 bps adverse execution per side), not verified Singapore account tariffs. Full market fills, deep liquidity and USDT/USD parity are assumptions. No historical order-book reconstruction, real-money orders or broker paper-account fills were obtained. Weekly profits are not promised.
