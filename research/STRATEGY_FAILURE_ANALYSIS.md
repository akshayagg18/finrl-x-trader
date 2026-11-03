# Strategy failure analysis

**Conclusion: the existing strategies fail primarily because their raw signals are weak or unstable. Costs magnify the damage in high-turnover variants, but costs are not the sole cause. No implementation defect was found that turns a losing result into a credible winner.**

Evidence comes from retained JSON/CSV artifacts, not handoff claims. Historical periods have already been inspected and are development evidence.

## Measured failure modes

| Strategy | Gross evidence | Net evidence | Activity / exposure | Diagnosis |
|---|---:|---:|---:|---|
| Daily selected rotation | Same-trade gross was not retained | -2.82% final; -10.57% with $1/order | 41 orders; material cash allocation | Selection did not generalize. Default +1.67%, SPY +13.89%, QQQ +14.51% on the same period. Fixed costs are severe at $500, but base-cost underperformance already exists. |
| BTC 15m momentum | -4.41% zero-cost rerun | -14.19% | 90 fills | Raw signal lost before fees; turnover then deepened the loss. |
| ETH 15m momentum | -7.53% zero-cost rerun | -15.40% | 90 fills | Same failure: negative gross edge plus cost drag. |
| AAPL 15m momentum | +0.58% zero-cost rerun | -0.12% | 36 fills | Small gross edge was below estimated execution costs; 2x costs produced -0.90%. |
| SPY / QQQ intraday | 0% | 0% | 0 fills | Whole-share price exceeded the $400 allocation. This is an affordability constraint, not profitable abstention. |
| Intraday ML | Some short folds positive; e.g. BTC 15m Jan-Feb gross +3.30% versus net +0.03% | Mostly flat/negative; every selected October model 0% | October: 0 fills for all four symbol/interval selections | Validation winners had very small samples. Forecast shrinkage plus 40-60 bp locked hurdles produced abstention after refitting. |
| Growth ML | -2.49% same-trade gross | -3.35%; -4.13% at 2x costs | 17 exits; 48/51 complete weeks flat | The signal itself lost money. Costs ($2.87 fees and $1.43 modeled friction) worsened, but did not cause, failure. Only one monthly candidate qualified and then failed after deployment. |
| New paper-style hourly XGBoost mechanism | Not separately rerun cost-free | -5.55% | 4 completed trades; 3.19% time invested | It hit the 8% portfolio halt. Directional forecasts and rare large signals were not stable in the local spot sample. |

Gross and net intraday reruns can have different sizes and halt times, so their difference is diagnostic rather than an exact fee add-back.

## Previous zero-trade models

The four retained October artifacts show:

| Model | Locked hurdle | Recorded fills | Execution/risk blocks |
|---|---:|---:|---:|
| BTC 5m, 16 bars | 0.60% | 0 | 0 |
| BTC 15m, 8 bars | 0.60% | 0 | 0 |
| ETH 5m, 8 bars | 0.60% | 0 | 0 |
| ETH 15m, 8 bars | 0.40% | 0 | 0 |

The hurdle is estimated round-trip cost (0.30%) plus the selected ML buffer (0.10% or 0.30%). Zero execution blocks rules out minimum notional, quantity, cash, and portfolio-risk rejection after order formation. The retained historical JSON did not save forecasts, and the ignored runtime model binaries are absent; therefore the exact old forecast distribution cannot be reconstructed honestly on this host. This evidence narrows the cause to forecast/hurdle/state abstention, not execution affordability.

The new implementation fixes the observability gap. Each fold saves raw forecasts, hurdles, regimes, actions, and rejection reasons in `research/profitability/*_forecasts.csv.gz`.

In the new final strategy holdout:

- 2,206 forecasts were evaluated.
- 900 were positive gross candidates.
- 0 cleared the net cost-plus-uncertainty hurdle.
- 0 were rejected by risk or minimum-notional controls.
- 0 orders and 0 fills occurred.
- Forecast maximum was 0.2035%; the frozen entry hurdle was 0.4827% (0.30% round-trip cost plus 0.1827% median calibration error).
- Directional accuracy was 49.73%; Spearman correlation was -0.0164.

This is legitimate cash abstention, **not** evidence of profitability.

## Signal, cost, timing, and sizing assessment

1. **Weak signals:** Gross BTC/ETH momentum and growth results were negative. New forecast correlations cluster near zero (-0.042 to +0.018 across interval screens).
2. **Costs versus movement:** Short-interval turnover consumes small predicted moves. The AAPL gross/net reversal and BTC ML gross/net gap are direct examples.
3. **Model selection instability:** Small validation samples selected sparse configurations. The development `1h -> 1h` screen gained 3.22% from one trade and was explicitly rejected by the sample gate.
4. **Execution alignment:** New labels use a completed bar, fill at the next open, and mature at the future exit open. Automated tests perturb future rows and verify earlier features do not change.
5. **Sizing:** Crypto minimums are feasible for $500. Previous ETF zero trades were whole-share affordability; the new equity pilot uses fractional sizing. No leverage is used.
6. **Risk rules:** The new final model had zero risk rejections. The paper-style mechanism did reach the 8% halt, correctly preventing additional exposure rather than manufacturing recovery trades.
7. **Regimes and sizing:** On development OOS, the chosen hourly configuration's trend filter made no difference; volatility sizing reduced its one-trade gain from 3.22% to 2.16% and drawdown from 3.11% to 2.09%. One trade is inadequate evidence for either choice.

## Data and evidence limits

- Crypto: genuine OKX spot candles, 2024-11-01 through 2026-10-31.
- Equities: only AAPL, SPY, and QQQ, roughly 60 sessions; not adequate for a broad-universe ORB conclusion.
- Previously viewed dates are not pristine market holdouts.
- Historical spreads and depth are unavailable; costs are conservative fixed estimates.
- Old ML forecast arrays were not retained. This is now corrected prospectively, not backfilled with invented values.
