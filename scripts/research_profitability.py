"""Run the predeclared cost-aware BTC study and constrained equity comparison.

The repository's dates were inspected by earlier work, so even the newly frozen
August-October 2026 strategy test is labelled a strategy-level holdout rather
than pristine market evidence.  No result from this script enables trading.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
import xgboost

from trader.opening_range import opening_range_backtest
from trader.profitability import (
    ExecutionConfig,
    aligned_target,
    fit_xgboost,
    forecast_metrics,
    passive_buy_and_hold,
    predict,
    regime_frame,
    resample_ohlcv,
    simulate,
)

OUT = Path("research/profitability")
OUT.mkdir(parents=True, exist_ok=True)
BASE_EXECUTION = ExecutionConfig()
SCREEN_TRAIN_START = pd.Timestamp("2024-11-01", tz="UTC")
SCREEN_VALIDATION_START = pd.Timestamp("2025-08-01", tz="UTC")
SCREEN_TEST_START = pd.Timestamp("2025-11-01", tz="UTC")
SCREEN_TEST_END = pd.Timestamp("2026-08-01", tz="UTC")
FINAL_START = pd.Timestamp("2026-08-01", tz="UTC")
FINAL_END = pd.Timestamp("2026-11-01", tz="UTC")


def load_local(symbol: str, interval: int) -> pd.DataFrame:
    """Read the immutable research CSV without importing native broker engines."""
    path = Path("research/intraday/data") / f"{symbol}_{interval}m.csv"
    frame = pd.read_csv(path, parse_dates=["timestamp"]).set_index("timestamp")
    frame.index = pd.DatetimeIndex(frame.index).tz_convert("UTC")
    frame = frame[["open", "high", "low", "close", "volume"]].astype(float).sort_index()
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError(f"Invalid timestamp ordering in {path}")
    return frame


def json_dump(path: Path, value) -> None:
    path.write_text(json.dumps(_clean(value), indent=2, sort_keys=True))


def choose_execution(
    df,
    forecasts,
    horizon,
    validation_start,
    test_start,
    regimes,
    *,
    cost_rule="spot_round_trip",
):
    validation_start = pd.Timestamp(validation_start)
    test_start = pd.Timestamp(test_start)
    calibration_end = validation_start + (test_start - validation_start) / 2
    actual, _ = aligned_target(df, horizon)
    calibration = (forecasts.index >= validation_start) & (forecasts.index < calibration_end)
    # The caller adds horizon-specific residuals when available.  This fallback
    # keeps uncertainty conservative and deterministic.
    uncertainty = float((forecasts[calibration] - actual[calibration]).abs().median())
    if not np.isfinite(uncertainty):
        uncertainty = 0.0
    candidates = []
    for threshold in (1.0, 2.0, 3.0):
        for regime in ("all", "trending"):
            for sizing in ("fixed_percent", "volatility"):
                execution = replace(BASE_EXECUTION, sizing=sizing)
                result = simulate(
                    df,
                    forecasts,
                    calibration_end,
                    test_start,
                    execution=execution,
                    threshold_multiplier=threshold,
                    uncertainty=uncertainty,
                    cost_rule=cost_rule,
                    regime_filter=regime,
                    regimes=regimes,
                )
                candidates.append(
                    {
                        "threshold_multiplier": threshold,
                        "regime_filter": regime,
                        "sizing": sizing,
                        "uncertainty": uncertainty,
                        **result["metrics"],
                    }
                )
    active = [x for x in candidates if x["completed_trades"] >= 3]
    pool = active or candidates
    winner = max(pool, key=lambda x: (x["net_return"], x["max_drawdown"]))
    return winner, candidates


def evaluate_configuration(base, interval, horizon, name):
    df = resample_ohlcv(base, interval)
    model, meta = fit_xgboost(
        df,
        horizon,
        SCREEN_TRAIN_START,
        SCREEN_VALIDATION_START,
    )
    forecasts = predict(model, df)
    regimes = regime_frame(
        df,
        df.index[(df.index >= SCREEN_TRAIN_START) & (df.index < SCREEN_VALIDATION_START)],
    )
    selected, candidates = choose_execution(
        df, forecasts, horizon, SCREEN_VALIDATION_START, SCREEN_TEST_START, regimes
    )
    execution = replace(BASE_EXECUTION, sizing=selected["sizing"])
    baseline = simulate(
        df,
        forecasts,
        SCREEN_TEST_START,
        SCREEN_TEST_END,
        execution=execution,
        threshold_multiplier=selected["threshold_multiplier"],
        uncertainty=selected["uncertainty"],
        regime_filter=selected["regime_filter"],
        regimes=regimes,
    )
    ablations = {}
    for regime in ("all", "trending"):
        for sizing in ("fixed_percent", "volatility"):
            label = f"{regime}_{sizing}"
            ablations[label] = simulate(
                df,
                forecasts,
                SCREEN_TEST_START,
                SCREEN_TEST_END,
                execution=replace(BASE_EXECUTION, sizing=sizing),
                threshold_multiplier=selected["threshold_multiplier"],
                uncertainty=selected["uncertainty"],
                regime_filter=regime,
                regimes=regimes,
            )["metrics"]
    stress = {}
    for label, multiplier in (("cost_1.5x", 1.5), ("cost_2x", 2.0)):
        stressed = replace(
            execution,
            fee_bps=execution.fee_bps * multiplier,
            slippage_bps=execution.slippage_bps * multiplier,
        )
        stress[label] = simulate(
            df,
            forecasts,
            SCREEN_TEST_START,
            SCREEN_TEST_END,
            execution=stressed,
            threshold_multiplier=selected["threshold_multiplier"],
            uncertainty=selected["uncertainty"],
            regime_filter=selected["regime_filter"],
            regimes=regimes,
        )["metrics"]
    actual, _ = aligned_target(df, horizon)
    mask = (df.index >= SCREEN_TEST_START) & (df.index < SCREEN_TEST_END)
    return {
        "name": name,
        "interval_minutes": interval,
        "horizon_bars": horizon,
        "horizon_minutes": interval * horizon,
        "model": meta,
        "selected_on_validation": selected,
        "validation_candidates": candidates,
        "development_oos": _without_diagnostics(baseline),
        "development_ablations": ablations,
        "forecast_metrics": forecast_metrics(actual[mask], forecasts[mask]),
        "cost_1.5x": stress["cost_1.5x"],
        "cost_2x": stress["cost_2x"],
    }


def walk_forward_selected(base, interval, horizon):
    df = resample_ohlcv(base, interval)
    folds = []
    for number, test_start in enumerate(
        pd.date_range("2025-11-01", "2026-08-01", freq="3MS", tz="UTC"), start=1
    ):
        validation_start = test_start - pd.DateOffset(months=3)
        train_start = validation_start - pd.DateOffset(months=9)
        test_end = test_start + pd.DateOffset(months=3)
        model, meta = fit_xgboost(df, horizon, train_start, validation_start)
        validation_forecasts = predict(model, df)
        regimes = regime_frame(
            df,
            df.index[(df.index >= train_start) & (df.index < validation_start)],
        )
        selected, candidates = choose_execution(
            df, validation_forecasts, horizon, validation_start, test_start, regimes
        )
        # Paper protocol: after validation selection, refit on all information
        # whose labels matured before the test boundary.
        final_model, final_meta = fit_xgboost(df, horizon, train_start, test_start)
        forecasts = predict(final_model, df)
        execution = replace(BASE_EXECUTION, sizing=selected["sizing"])
        result = simulate(
            df,
            forecasts,
            test_start,
            test_end,
            execution=execution,
            threshold_multiplier=selected["threshold_multiplier"],
            uncertainty=selected["uncertainty"],
            regime_filter=selected["regime_filter"],
            regimes=regimes,
        )
        cost_stress = {}
        for label, multiplier in (("cost_1.5x", 1.5), ("cost_2x", 2.0)):
            stressed_execution = replace(
                execution,
                fee_bps=execution.fee_bps * multiplier,
                slippage_bps=execution.slippage_bps * multiplier,
            )
            cost_stress[label] = simulate(
                df,
                forecasts,
                test_start,
                test_end,
                execution=stressed_execution,
                threshold_multiplier=selected["threshold_multiplier"],
                uncertainty=selected["uncertainty"],
                regime_filter=selected["regime_filter"],
                regimes=regimes,
            )["metrics"]
        actual, _ = aligned_target(df, horizon)
        mask = (df.index >= test_start) & (df.index < test_end)
        pd.DataFrame(result["diagnostics"]).to_csv(
            OUT / f"selected_fold_{number}_forecasts.csv.gz", index=False, compression="gzip"
        )
        folds.append(
            {
                "fold": number,
                "train_start": str(train_start),
                "validation_start": str(validation_start),
                "test_start": str(test_start),
                "test_end": str(test_end),
                "selection_model": meta,
                "test_model": final_meta,
                "selected_on_validation": selected,
                "validation_candidates": candidates,
                "forecast_metrics": forecast_metrics(actual[mask], forecasts[mask]),
                "result": _without_diagnostics(result),
                "cost_1.5x": cost_stress["cost_1.5x"],
                "cost_2x": cost_stress["cost_2x"],
                "is_final_strategy_holdout": number == 4,
            }
        )
    return folds


def paper_mechanism(base):
    df = resample_ohlcv(base, 60)
    model, meta = fit_xgboost(
        df,
        1,
        SCREEN_TRAIN_START,
        SCREEN_VALIDATION_START,
        paper_scale=True,
    )
    forecasts = predict(model, df)
    regimes = regime_frame(df, df.index[df.index < SCREEN_VALIDATION_START])
    result = simulate(
        df,
        forecasts,
        SCREEN_TEST_START,
        SCREEN_TEST_END,
        execution=BASE_EXECUTION,
        threshold_multiplier=2.0,
        uncertainty=0.0,
        cost_rule="paper_position_change",
        regime_filter="all",
        regimes=regimes,
    )
    stress = {}
    for label, multiplier in (("cost_1.5x", 1.5), ("cost_2x", 2.0)):
        stress[label] = simulate(
            df,
            forecasts,
            SCREEN_TEST_START,
            SCREEN_TEST_END,
            execution=replace(
                BASE_EXECUTION,
                fee_bps=BASE_EXECUTION.fee_bps * multiplier,
                slippage_bps=BASE_EXECUTION.slippage_bps * multiplier,
            ),
            threshold_multiplier=2.0,
            uncertainty=0.0,
            cost_rule="paper_position_change",
            regime_filter="all",
            regimes=regimes,
        )["metrics"]
    pd.DataFrame(result["diagnostics"]).to_csv(
        OUT / "paper_mechanism_forecasts.csv.gz", index=False, compression="gzip"
    )
    return {"model": meta, "result": _without_diagnostics(result), **stress}


def baselines(base, interval, horizon, selected):
    df = resample_ohlcv(base, interval)
    eth = resample_ohlcv(load_local("ETH-USDT", 5), interval)
    regimes = regime_frame(df, df.index[df.index < FINAL_START])
    index = df.index
    momentum = df.close.pct_change(max(1, int(24 * 60 / interval))).fillna(0)
    common = dict(
        start=FINAL_START,
        end=FINAL_END,
        execution=BASE_EXECUTION,
        threshold_multiplier=1.0,
        uncertainty=0.0,
        regime_filter="all",
        regimes=regimes,
    )
    btc_hold = passive_buy_and_hold(df, FINAL_START, FINAL_END)
    eth_hold = passive_buy_and_hold(eth, FINAL_START, FINAL_END)
    trend = simulate(df, momentum, cost_rule="spot_round_trip", **common)
    mean_reversion = simulate(df, -momentum, cost_rule="spot_round_trip", **common)
    metrics = {
        "cash": {"net_return": 0.0, "net_profit_usd": 0.0, "max_drawdown": 0.0, "completed_trades": 0},
        "btc_buy_hold_60pct": btc_hold["metrics"],
        "eth_buy_hold_60pct": eth_hold["metrics"],
        "simple_24h_momentum": trend["metrics"],
        "simple_24h_mean_reversion": mean_reversion["metrics"],
    }
    curves = {
        "BTC buy-and-hold": btc_hold["points"],
        "ETH buy-and-hold": eth_hold["points"],
        "BTC momentum": trend["points"],
        "BTC mean reversion": mean_reversion["points"],
    }
    return metrics, curves


def equity_opening_range():
    data = {s: load_local(s, 15) for s in ("AAPL", "SPY", "QQQ")}
    result = opening_range_backtest(data)
    spy = data["SPY"]
    equity_execution = replace(
        BASE_EXECUTION,
        fee_bps=0.0,
        slippage_bps=3.0,
    )
    pd.DataFrame(result["diagnostics"]).to_csv(OUT / "orb_signal_diagnostics.csv", index=False)
    return {
        **_without_diagnostics(result),
        "spy_buy_hold_60pct": passive_buy_and_hold(
            spy,
            spy.index[0],
            spy.index[-1] + pd.Timedelta("15min"),
            execution=equity_execution,
        )["metrics"],
        "cost_1.5x": opening_range_backtest(data, friction_bps=4.5)["metrics"],
        "cost_2x": opening_range_backtest(data, friction_bps=6.0)["metrics"],
    }


def legacy_zero_trade_diagnostics():
    """Audit the retained artifacts without inventing absent raw forecasts."""
    output = []
    for symbol in ("BTC-USDT", "ETH-USDT"):
        for interval in (5, 15):
            locked = json.loads(
                Path(f"research/intraday_ml/{symbol}_{interval}_locked.json").read_text()
            )["selected"]
            family = locked["family"]
            horizon = int(locked["horizon"])
            buffer = float(locked["config"]["ml_buffer"])
            artifact_path = Path(
                f"research/intraday_ml/{symbol}_{interval}_2026-10-01_ml.json.gz"
            )
            with gzip.open(artifact_path, "rt") as handle:
                artifact = json.load(handle)
            round_trip = 2 * (10 + 5) / 10_000
            final_hurdle = round_trip + buffer
            output.append(
                {
                    "symbol": symbol,
                    "interval_minutes": interval,
                    "family": family,
                    "horizon_bars": horizon,
                    "ml_buffer": buffer,
                    "forecast_distribution_available": False,
                    "forecast_distribution_gap": "Historical JSON omitted forecasts and runtime model binaries are intentionally excluded from Git; exact reconstruction is blocked by this host's native-library application policy",
                    "round_trip_cost": round_trip,
                    "final_hurdle": final_hurdle,
                    "execution_blocks": len(artifact.get("blocked", [])),
                    "recorded_fills": len(artifact["fills"]),
                    "recorded_net_return": artifact["net_return"],
                    "diagnosis": "No signal reached order submission; zero execution blocks rule out quantity, minimum-notional, and portfolio-risk rejection after submission. The retained artifact cannot distinguish sub-threshold forecasts from model state/cooldown abstention.",
                }
            )
    json_dump(OUT / "legacy_zero_trade_diagnostics.json", output)
    return output


def charts(final_result, baseline_curves):
    plt.style.use("seaborn-v0_8-darkgrid")
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    points = pd.DataFrame(final_result["points"])
    points["timestamp"] = pd.to_datetime(points.timestamp, utc=True)
    axes[0].plot(points.timestamp, points.equity, label="Selected cost-aware XGBoost")
    axes[1].plot(points.timestamp, points.equity / points.equity.cummax() - 1, label="Selected XGBoost")
    for label, raw in baseline_curves.items():
        curve = pd.DataFrame(raw)
        curve["timestamp"] = pd.to_datetime(curve.timestamp, utc=True)
        axes[0].plot(curve.timestamp, curve.equity, linewidth=1.0, label=label)
        axes[1].plot(
            curve.timestamp,
            curve.equity / curve.equity.cummax() - 1,
            linewidth=1.0,
            label=label,
        )
    axes[0].axhline(500, color="black", linewidth=0.8, linestyle="--", label="Cash")
    axes[0].set_ylabel("USD")
    axes[0].legend(ncol=2, fontsize=8)
    axes[1].set_ylabel("Drawdown")
    axes[1].set_xlabel("UTC")
    axes[1].legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "selected_equity_drawdown.png", dpi=150)
    plt.close(fig)


def run():
    base = load_local("BTC-USDT", 5)
    protocol = {
        "created": pd.Timestamp.now(tz="UTC").isoformat(),
        "capital": 500,
        "market": "BTC-USDT spot",
        "data": {
            "source": "OKX public spot candles",
            "first": str(base.index[0]),
            "last": str(base.index[-1]),
            "bars": len(base),
            "sha256": hashlib.sha256(Path("research/intraday/data/BTC-USDT_5m.csv").read_bytes()).hexdigest(),
        },
        "screen": {
            "train": [str(SCREEN_TRAIN_START), str(SCREEN_VALIDATION_START)],
            "validation": [str(SCREEN_VALIDATION_START), str(SCREEN_TEST_START)],
            "development_oos": [str(SCREEN_TEST_START), str(SCREEN_TEST_END)],
            "final_strategy_holdout": [str(FINAL_START), str(FINAL_END)],
        },
        "warning": "All market dates were exposed to earlier repository research; final is untouched by this strategy's selection, not a pristine market holdout.",
        "costs_per_side_bps": {"fee": 10, "slippage_and_spread": 5},
        "risk": {"max_exposure": 0.60, "daily_loss_pause": 0.02, "drawdown_halt": 0.08, "leverage": 0},
    }
    json_dump(OUT / "protocol.json", protocol)
    matrix = [
        (5, 48, "5m_to_4h"),
        (15, 16, "15m_to_4h"),
        (30, 8, "30m_to_4h"),
        (60, 1, "1h_to_1h"),
        (60, 4, "1h_to_4h"),
        (240, 1, "4h_to_4h"),
    ]
    screening = []
    for interval, horizon, name in matrix:
        print(f"screening {name}", flush=True)
        screening.append(evaluate_configuration(base, interval, horizon, name))
        # Keep the dashboard/API artifact small. Full bar-by-bar equity points
        # remain available in the compressed audit registry written below.
        json_dump(OUT / "screening.json", _compact_for_json(screening))
    qualified = [
        x
        for x in screening
        if x["development_oos"]["metrics"]["completed_trades"] >= 10
        and x["development_oos"]["metrics"]["net_return"] > 0
        and x["cost_1.5x"]["net_return"] > 0
    ]
    selection_pool = qualified or screening
    selected = max(
        selection_pool,
        key=lambda x: (
            x["development_oos"]["metrics"]["net_return"],
            x["development_oos"]["metrics"]["max_drawdown"],
        ),
    )
    frozen = {
        "name": selected["name"],
        "interval_minutes": selected["interval_minutes"],
        "horizon_bars": selected["horizon_bars"],
        "selection_rule": "Positive development OOS and 1.5x cost with >=10 trades, then highest return; otherwise highest return with no qualification claim",
        "qualified_at_selection": bool(qualified),
    }
    json_dump(OUT / "selection_locked.json", frozen)
    print(f"walk-forward selected {frozen['name']}", flush=True)
    folds = walk_forward_selected(base, frozen["interval_minutes"], frozen["horizon_bars"])
    final_result = folds[-1]["result"]
    benchmark, benchmark_curves = baselines(
        base, frozen["interval_minutes"], frozen["horizon_bars"], selected
    )
    paper = paper_mechanism(base)
    orb = equity_opening_range()
    legacy_zero = legacy_zero_trade_diagnostics()
    charts(final_result, benchmark_curves)
    summary = {
        "protocol": protocol,
        "screening": screening,
        "selection_locked": frozen,
        "walk_forward_folds": folds,
        "final_strategy_holdout": final_result,
        "final_baselines": benchmark,
        "paper_mechanism_replication": paper,
        "equity_orb_adaptation": orb,
        "legacy_zero_trade_diagnostics": legacy_zero,
        "experiment_count": int(
            len(screening) * (12 + 1 + 4 + 2)  # validation grid, OOS base, ablations, stress
            + len(folds) * (12 + 1 + 2)  # validation grid, OOS base, stress
            + 3  # paper mechanism base and two cost stresses
            + 3  # equity ORB base and two cost stresses
            + 6  # final cash, BTC/ETH hold, momentum/mean reversion, SPY hold
        ),
        "environment": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "sklearn": sklearn.__version__,
            "xgboost": xgboost.__version__,
        },
    }
    json_dump(OUT / "summary.json", _compact_for_json(summary))
    with gzip.open(OUT / "full_results.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(_clean(summary), handle)
    print(json.dumps(_clean({
        "selected": frozen,
        "final": final_result["metrics"],
        "baselines": benchmark,
        "orb": orb["metrics"],
        "experiments": summary["experiment_count"],
    }), indent=2), flush=True)


def _without_diagnostics(result):
    return {k: v for k, v in result.items() if k != "diagnostics"}


def _compact_for_json(value):
    """Strip large per-bar arrays from human/API JSON, preserving all metrics."""
    if isinstance(value, dict):
        return {
            k: _compact_for_json(v)
            for k, v in value.items()
            if k not in {"diagnostics", "points"}
        }
    if isinstance(value, (list, tuple)):
        return [_compact_for_json(v) for v in value]
    return value


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    return value


if __name__ == "__main__":
    run()
