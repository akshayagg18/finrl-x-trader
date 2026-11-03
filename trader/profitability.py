"""Leakage-controlled, cost-aware research primitives.

This module is deliberately disconnected from broker submission.  A signal is
formed from a completed bar, filled at the following bar open, and marked on
subsequent opens.  It is shared by the reproducible research script and the
dashboard's read-only experiment endpoint.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExecutionConfig:
    capital: float = 500.0
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    max_exposure: float = 0.60
    min_notional: float = 1.0
    daily_loss_limit: float = 0.02
    drawdown_halt: float = 0.08
    sizing: str = "fixed_percent"
    fixed_dollars: float = 300.0
    target_annual_vol: float = 0.50

    @property
    def one_way_cost(self) -> float:
        return (self.fee_bps + self.slippage_bps) / 10_000


def resample_ohlcv(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate completed bars without filling missing observations."""
    if minutes not in (5, 15, 30, 60, 240):
        raise ValueError("Unsupported interval")
    source_minutes = int((df.index[1] - df.index[0]).total_seconds() / 60)
    if minutes < source_minutes or minutes % source_minutes:
        raise ValueError("Interval is incompatible with source data")
    expected = minutes // source_minutes
    rule = f"{minutes}min"
    counts = df["close"].resample(rule).count()
    out = df.resample(rule).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return out.loc[counts == expected].dropna()


def feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Features available at the close of each indexed, completed bar."""
    close = df["close"].astype(float)
    log_return = np.log(close).diff()
    out = pd.DataFrame(index=df.index)
    for lag in (1, 2, 3, 6, 12, 24, 48):
        out[f"return_lag_{lag}"] = log_return.shift(lag - 1)
    for window in (6, 12, 24, 48, 72, 168):
        out[f"momentum_{window}"] = close.pct_change(window)
        out[f"volatility_{window}"] = log_return.rolling(window).std()
        out[f"sma_distance_{window}"] = close / close.rolling(window).mean() - 1
    prior_close = close.shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prior_close).abs(),
            (df["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr_ratio_24"] = true_range.rolling(24).mean() / close
    out["range"] = (df["high"] - df["low"]) / close
    span = (df["high"] - df["low"]).replace(0, np.nan)
    out["close_location"] = (close - df["low"]) / span
    volume = df["volume"].astype(float)
    out["volume_change"] = np.log1p(volume).diff()
    out["relative_volume_24"] = volume / volume.rolling(24).mean() - 1
    out["relative_volume_168"] = volume / volume.rolling(168).mean() - 1
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((loss == 0) & (gain == 0), 50.0)
    out["rsi_14"] = rsi
    out["hour_sin"] = np.sin(2 * np.pi * df.index.hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * df.index.hour / 24)
    out["day_sin"] = np.sin(2 * np.pi * df.index.dayofweek / 7)
    out["day_cos"] = np.cos(2 * np.pi * df.index.dayofweek / 7)
    return out.replace([np.inf, -np.inf], np.nan)


def aligned_target(df: pd.DataFrame, horizon: int) -> tuple[pd.Series, pd.Series]:
    """Return from the next tradable open through ``horizon`` bars later.

    At row t the current bar has just completed.  Execution is at open[t+1],
    and label maturity is open[t+horizon+1].
    """
    if horizon < 1:
        raise ValueError("horizon must be positive")
    target = df["open"].shift(-(horizon + 1)) / df["open"].shift(-1) - 1
    maturity = pd.Series(df.index, index=df.index).shift(-(horizon + 1))
    return target, maturity


def fit_xgboost(
    df: pd.DataFrame,
    horizon: int,
    train_start,
    cutoff,
    *,
    seed: int = 17,
    paper_scale: bool = False,
):
    """Fit only examples whose labels have matured strictly before cutoff."""
    from xgboost import XGBRegressor

    start = _utc(train_start)
    end = _utc(cutoff)
    x = feature_frame(df)
    y, maturity = aligned_target(df, horizon)
    valid = (
        (x.index >= start)
        & (x.index < end)
        & x.notna().all(axis=1)
        & y.notna()
        & (maturity < end)
    )
    x_train, y_train = x.loc[valid], y.loc[valid]
    if len(x_train) < 1_000:
        raise ValueError("Need at least 1,000 matured observations")
    # Values sit inside the paper's published search space.  The compact spot
    # study uses fewer estimators to keep the full experiment reproducible on a
    # normal PC; paper_scale uses the published lower bound of 1,000.
    model = XGBRegressor(
        objective="reg:squarederror",
        n_estimators=1_000 if paper_scale else 350,
        max_depth=3,
        learning_rate=0.02,
        min_child_weight=20,
        subsample=0.75,
        colsample_bytree=0.75,
        reg_alpha=0.001,
        reg_lambda=10,
        n_jobs=4,
        random_state=seed,
        tree_method="hist",
    )
    model.fit(x_train, y_train, verbose=False)
    return model, {
        "rows": int(len(x_train)),
        "training_start": str(x_train.index[0]),
        "last_feature": str(x_train.index[-1]),
        "last_label_maturity": str(maturity.loc[x_train.index[-1]]),
        "cutoff": str(end),
        "horizon_bars": horizon,
        "features": list(x_train.columns),
        "xgboost_params": model.get_params(),
    }


def predict(model, df: pd.DataFrame) -> pd.Series:
    x = feature_frame(df)
    valid = x.notna().all(axis=1)
    result = pd.Series(np.nan, index=df.index, name="prediction")
    if valid.any():
        result.loc[valid] = model.predict(x.loc[valid])
    return result


def regime_frame(df: pd.DataFrame, calibration_index: Iterable | None = None) -> pd.DataFrame:
    """Simple causal trend/volatility/volume regimes.

    Median boundaries are learned from the supplied past calibration index and
    then frozen.  If omitted, expanding medians are used for diagnostics only.
    """
    close = df["close"].astype(float)
    ret = np.log(close).diff()
    trend_strength = (close / close.rolling(168).mean() - 1).abs()
    volatility = ret.rolling(168).std()
    liquidity = df["volume"] / df["volume"].rolling(168).median()
    if calibration_index is not None:
        idx = pd.Index(calibration_index)
        trend_cut = float(trend_strength.reindex(idx).median())
        vol_cut = float(volatility.reindex(idx).median())
        liq_cut = float(liquidity.reindex(idx).median())
        trend_cut = trend_cut if np.isfinite(trend_cut) else 0.0
        vol_cut = vol_cut if np.isfinite(vol_cut) else 0.0
        liq_cut = liq_cut if np.isfinite(liq_cut) else 1.0
        trending = trend_strength > trend_cut
        high_vol = volatility > vol_cut
        high_liquidity = liquidity > liq_cut
    else:
        trending = trend_strength > trend_strength.expanding(168).median()
        high_vol = volatility > volatility.expanding(168).median()
        high_liquidity = liquidity > liquidity.expanding(168).median()
    return pd.DataFrame(
        {
            "trending": trending.fillna(False),
            "high_volatility": high_vol.fillna(False),
            "high_liquidity": high_liquidity.fillna(False),
            "realized_volatility": volatility,
        },
        index=df.index,
    )


def simulate(
    df: pd.DataFrame,
    forecasts: pd.Series,
    start,
    end,
    *,
    execution: ExecutionConfig | None = None,
    threshold_multiplier: float = 2.0,
    minimum_edge: float = 0.0,
    uncertainty: float = 0.0,
    cost_rule: str = "spot_round_trip",
    regime_filter: str = "all",
    regimes: pd.DataFrame | None = None,
):
    """Run a long-only cash-account simulation with explicit rejection reasons."""
    c = execution or ExecutionConfig()
    if c.sizing not in ("fixed_percent", "fixed_dollar", "volatility"):
        raise ValueError("Unsupported sizing mode")
    lo, hi = _utc(start), _utc(end)
    idx = df.index[(df.index >= lo) & (df.index < hi)]
    # A row needs both the following execution open and the subsequent mark.
    idx = idx[idx < df.index[-2]]
    if not len(idx):
        raise ValueError("No evaluable rows")
    regimes = regimes if regimes is not None else regime_frame(df)
    cash, units = c.capital, 0.0
    entry_value = 0.0
    halted = False
    peak = c.capital
    current_day = None
    day_start = c.capital
    points, trades, diagnostics = [], [], []
    counts = {
        "forecasts": 0,
        "positive_forecasts": 0,
        "gross_candidate_signals": 0,
        "net_candidate_signals": 0,
        "regime_rejections": 0,
        "risk_rejections": 0,
        "minimum_notional_rejections": 0,
        "submitted_orders": 0,
        "simulated_fills": 0,
    }
    total_costs = total_turnover = invested_steps = 0.0
    entry_time = None
    for t in idx:
        loc = df.index.get_loc(t)
        execution_time = df.index[loc + 1]
        price = float(df["open"].iloc[loc + 1])
        mark = float(df["open"].iloc[loc + 2])
        equity_before = cash + units * price
        day = execution_time.date()
        if day != current_day:
            current_day, day_start = day, equity_before
        peak = max(peak, equity_before)
        daily_block = equity_before / day_start - 1 <= -c.daily_loss_limit
        if equity_before / peak - 1 <= -c.drawdown_halt:
            halted = True
        value = float(forecasts.get(t, np.nan))
        action = "hold" if units else "cash"
        reason = "position unchanged"
        if np.isfinite(value):
            counts["forecasts"] += 1
            counts["positive_forecasts"] += int(value > 0)
        if cost_rule == "paper_position_change":
            entry_hurdle = threshold_multiplier * c.one_way_cost + minimum_edge
            exit_hurdle = entry_hurdle
        elif cost_rule == "spot_round_trip":
            entry_hurdle = (
                threshold_multiplier * 2 * c.one_way_cost
                + minimum_edge
                + uncertainty
            )
            exit_hurdle = threshold_multiplier * c.one_way_cost + minimum_edge
        else:
            raise ValueError("Unsupported cost rule")
        if units == 0 and np.isfinite(value) and value > 0:
            counts["gross_candidate_signals"] += 1
            if value > entry_hurdle:
                counts["net_candidate_signals"] += 1
                allowed_regime = regime_filter == "all" or bool(
                    regimes.loc[t, "trending"]
                )
                if not allowed_regime:
                    counts["regime_rejections"] += 1
                    reason = "regime filter"
                elif halted or daily_block:
                    counts["risk_rejections"] += 1
                    reason = "portfolio risk control"
                else:
                    if c.sizing == "fixed_dollar":
                        budget = min(c.fixed_dollars, cash)
                    else:
                        exposure = c.max_exposure
                        if c.sizing == "volatility":
                            rv = float(regimes.loc[t, "realized_volatility"])
                            annual = rv * np.sqrt(365 * 24) if np.isfinite(rv) else np.inf
                            exposure *= min(1.0, c.target_annual_vol / annual)
                        budget = min(cash, equity_before * exposure)
                    if budget < c.min_notional:
                        counts["minimum_notional_rejections"] += 1
                        reason = "minimum notional"
                    else:
                        cost = budget * c.one_way_cost
                        units = budget / (price * (1 + c.one_way_cost))
                        cash -= budget
                        entry_value = budget
                        entry_time = execution_time
                        total_costs += cost
                        total_turnover += budget
                        counts["submitted_orders"] += 1
                        counts["simulated_fills"] += 1
                        action, reason = "buy", "forecast cleared net hurdle"
                        trades.append(
                            {
                                "timestamp": str(execution_time),
                                "side": "BUY",
                                "price": price * (1 + c.one_way_cost),
                                "notional": budget,
                                "cost": cost,
                            }
                        )
            else:
                reason = "forecast below net cost/uncertainty hurdle"
        elif units > 0 and (halted or (np.isfinite(value) and value < -exit_hurdle)):
            proceeds_mid = units * price
            cost = proceeds_mid * c.one_way_cost
            proceeds = proceeds_mid - cost
            cash += proceeds
            pnl = proceeds - entry_value
            total_costs += cost
            total_turnover += proceeds_mid
            counts["submitted_orders"] += 1
            counts["simulated_fills"] += 1
            trades.append(
                {
                    "timestamp": str(execution_time),
                    "side": "SELL",
                    "price": price * (1 - c.one_way_cost),
                    "notional": proceeds_mid,
                    "cost": cost,
                    "pnl": pnl,
                    "holding_hours": (
                        (execution_time - entry_time).total_seconds() / 3600
                        if entry_time is not None
                        else None
                    ),
                }
            )
            units = 0.0
            entry_value = 0.0
            entry_time = None
            action = "sell"
            reason = "risk halt" if halted else "negative forecast cleared exit hurdle"
        equity = cash + units * mark
        invested_steps += int(units > 0)
        points.append({"timestamp": str(df.index[loc + 2]), "equity": equity})
        diagnostics.append(
            {
                "signal_timestamp": str(t),
                "execution_timestamp": str(execution_time),
                "prediction": value,
                "entry_hurdle": entry_hurdle,
                "position_units": units,
                "equity": equity,
                "regime": "trending" if regimes.loc[t, "trending"] else "sideways",
                "volatility_regime": "high" if regimes.loc[t, "high_volatility"] else "low",
                "liquidity_regime": "high" if regimes.loc[t, "high_liquidity"] else "low",
                "action": action,
                "reason": reason,
            }
        )
    if units > 0:
        price = float(df.loc[idx[-1]:, "open"].iloc[2])
        proceeds_mid = units * price
        cost = proceeds_mid * c.one_way_cost
        cash += proceeds_mid - cost
        total_costs += cost
        total_turnover += proceeds_mid
        counts["submitted_orders"] += 1
        counts["simulated_fills"] += 1
        trades.append(
            {
                "timestamp": str(pd.Timestamp(points[-1]["timestamp"])),
                "side": "SELL",
                "price": price * (1 - c.one_way_cost),
                "notional": proceeds_mid,
                "cost": cost,
                "pnl": proceeds_mid - cost - entry_value,
                "holding_hours": (
                    (pd.Timestamp(points[-1]["timestamp"]) - entry_time).total_seconds()
                    / 3600
                    if entry_time is not None
                    else None
                ),
            }
        )
        units = 0.0
        points[-1]["equity"] = cash
    result = {
        "config": {
            **asdict(c),
            "threshold_multiplier": threshold_multiplier,
            "minimum_edge": minimum_edge,
            "uncertainty": uncertainty,
            "cost_rule": cost_rule,
            "regime_filter": regime_filter,
        },
        "start": str(lo),
        "end": str(hi),
        "initial": c.capital,
        "ending_equity": cash,
        "net_return": cash / c.capital - 1,
        "points": points,
        "trades": trades,
        "diagnostics": diagnostics,
        "signal_counts": counts,
        "total_costs": total_costs,
        "turnover_usd": total_turnover,
        "time_invested": invested_steps / len(idx),
        "halted": halted,
    }
    result["metrics"] = performance_metrics(result)
    return result


def performance_metrics(result: dict) -> dict:
    points = result["points"]
    series = pd.Series(
        [float(p["equity"]) for p in points],
        index=pd.to_datetime([p["timestamp"] for p in points], utc=True),
    )
    daily = series.resample("1D").last().dropna()
    returns = daily.pct_change().dropna()
    drawdown = series / series.cummax() - 1
    exits = [t for t in result["trades"] if t["side"] == "SELL"]
    pnl = [float(t.get("pnl", 0)) for t in exits]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    span_days = max(1.0, (series.index[-1] - series.index[0]).total_seconds() / 86400)
    std = float(returns.std()) if len(returns) else 0.0
    downside = float(np.sqrt(np.mean(np.minimum(returns, 0) ** 2))) if len(returns) else 0.0
    return {
        "net_profit_usd": float(series.iloc[-1] - result["initial"]),
        "net_return": float(series.iloc[-1] / result["initial"] - 1),
        "annualized_return": float((series.iloc[-1] / result["initial"]) ** (365 / span_days) - 1)
        if span_days >= 90
        else None,
        "max_drawdown": float(drawdown.min()),
        "sharpe": float(returns.mean() / std * np.sqrt(365)) if len(returns) >= 30 and std > 0 else None,
        "sortino": float(returns.mean() / downside * np.sqrt(365))
        if len(returns) >= 30 and downside > 0
        else None,
        "completed_trades": len(exits),
        "win_rate": len(wins) / len(pnl) if pnl else None,
        "profit_factor": sum(wins) / abs(sum(losses)) if losses else None,
        "average_net_profit_per_trade": float(np.mean(pnl)) if pnl else None,
        "average_gain": float(np.mean(wins)) if wins else None,
        "average_loss": float(np.mean(losses)) if losses else None,
        "average_holding_hours": float(np.mean([t["holding_hours"] for t in exits])) if exits else None,
        "total_costs": float(result["total_costs"]),
        "turnover": float(result["turnover_usd"] / series.mean()),
        "time_invested": float(result["time_invested"]),
    }


def passive_buy_and_hold(
    df: pd.DataFrame,
    start,
    end,
    *,
    execution: ExecutionConfig | None = None,
) -> dict:
    """Fractional, unlevered passive comparator with explicit entry/exit costs.

    Unlike an active strategy, this benchmark is not stopped by the daily-loss
    or drawdown controls. It therefore measures actual passive opportunity cost
    rather than a risk-managed approximation of buy-and-hold.
    """
    c = execution or ExecutionConfig()
    sample = df.loc[(_utc(start) <= df.index) & (df.index < _utc(end))]
    if len(sample) < 2:
        raise ValueError("Buy-and-hold requires at least two bars")
    entry_time, exit_time = sample.index[0], sample.index[-1]
    entry_mid = float(sample.open.iloc[0])
    exit_mid = float(sample.close.iloc[-1])
    budget = c.capital * c.max_exposure
    entry_cost = budget * c.one_way_cost
    units = budget / (entry_mid * (1 + c.one_way_cost))
    cash = c.capital - budget
    entry_value = units * entry_mid
    points = [
        {"timestamp": str(t), "equity": cash + units * float(price)}
        for t, price in sample.close.items()
    ]
    exit_gross = units * exit_mid
    exit_cost = exit_gross * c.one_way_cost
    ending = cash + exit_gross - exit_cost
    points[-1]["equity"] = ending
    result = {
        "config": {**asdict(c), "strategy": "passive_buy_and_hold"},
        "start": str(entry_time),
        "end": str(exit_time),
        "initial": c.capital,
        "ending_equity": ending,
        "net_return": ending / c.capital - 1,
        "points": points,
        "trades": [
            {
                "timestamp": str(entry_time),
                "side": "BUY",
                "price": entry_mid * (1 + c.one_way_cost),
                "notional": budget,
                "cost": entry_cost,
            },
            {
                "timestamp": str(exit_time),
                "side": "SELL",
                "price": exit_mid * (1 - c.one_way_cost),
                "notional": exit_gross,
                "cost": exit_cost,
                "pnl": exit_gross - exit_cost - budget,
                "holding_hours": (exit_time - entry_time).total_seconds() / 3600,
            },
        ],
        "diagnostics": [],
        "signal_counts": {"submitted_orders": 2, "simulated_fills": 2},
        "total_costs": entry_cost + exit_cost,
        "turnover_usd": entry_value + exit_gross,
        "time_invested": 1.0,
        "halted": False,
    }
    result["metrics"] = performance_metrics(result)
    return result


def forecast_metrics(actual: pd.Series, predicted: pd.Series) -> dict:
    pair = pd.concat([actual.rename("actual"), predicted.rename("predicted")], axis=1).dropna()
    if not len(pair):
        return {"observations": 0}
    error = pair.predicted - pair.actual
    return {
        "observations": int(len(pair)),
        "prediction_mean": float(pair.predicted.mean()),
        "prediction_std": float(pair.predicted.std()),
        "prediction_min": float(pair.predicted.min()),
        "prediction_median": float(pair.predicted.median()),
        "prediction_max": float(pair.predicted.max()),
        "actual_mean": float(pair.actual.mean()),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "directional_accuracy": float((np.sign(pair.predicted) == np.sign(pair.actual)).mean()),
        "spearman": float(pair.corr(method="spearman").iloc[0, 1]),
    }


def _utc(value) -> pd.Timestamp:
    value = pd.Timestamp(value)
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")
