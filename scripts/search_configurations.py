"""Reproducible staged search; no broker access or deployed-settings mutation."""

import argparse
import hashlib
import itertools
import json
import math
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from trader.backtest import run_backtest
from trader.config import Settings
from trader.data import REQUIRED, MarketData
from trader.db import DB, dumps
from trader.strategies import StrategyEngine

OUT = Path("research/configuration_search_2026-11-03")
SNAPSHOT = OUT / "fresh_data"
STATE = Path("runtime/configuration_search")
PROTOCOL = {
    "seed": 0,
    "initial_capital": 500,
    "universe": Settings().strategy.universe,
    "training_folds": [["2022-01-03", "2022-12-30"], ["2023-01-03", "2023-12-29"]],
    "validation": ["2024-01-02", "2024-12-31"],
    "selection": "Maximum compounded return over the two training folds, subject to <=20% observed drawdown in each; top 8 plus baseline advance. Validation chooses highest return among candidates with <=20% drawdown. No test-period retuning.",
    "previously_seen_test": ["2025-01-02", "2025-10-07"],
    "fresh_test": ["2025-10-08", "2026-10-30"],
    "costs": {"slippage_bps": 5, "spread_bps": 4, "fixed_commission": 0},
    "stress_costs": [
        {"slippage_bps": 20, "spread_bps": 10, "commission_fixed": 0},
        {"slippage_bps": 5, "spread_bps": 4, "commission_fixed": 1},
    ],
    "limitations": [
        "Fixed present-day universe and adjusted vendor snapshot carry survivorship/revision bias.",
        "2025 baseline results previously inspected; this interval is excluded from selection but not claimed as fully unseen.",
        "Fresh period is evaluated only after the selection file is written.",
        "Small search and a single validation year cannot establish an ideal future configuration.",
        "Training folds reset capital and state; their compounded score is a selection statistic, not a continuous-account return.",
    ],
}


def configs():
    result = {"baseline": Settings()}
    profiles = [
        ("reserve40", 0.6, 0.3),
        ("reserve20", 0.8, 0.45),
        ("reserve05", 0.95, 0.6),
    ]
    for profile, deployment, vol in profiles:
        for cadence, stop, trail, top in itertools.product(
            ["weekly", "monthly"], [0.08, 0.15], [None, 0.15], [1, 2]
        ):
            s = Settings()
            s.capital.deployment = deployment
            s.capital.cash_reserve = 1 - deployment
            s.risk.volatility_target = vol
            s.risk.max_holdings = 12
            s.risk.max_order = 125
            s.risk.max_turnover = 0.75
            s.risk.max_daily_loss = 0.05
            s.risk.max_drawdown = 0.20
            s.risk.max_capital_loss = 0.20
            s.risk.loss_action = "liquidate"
            s.risk.stop_loss = stop
            s.risk.trailing_stop = trail
            s.strategy.rebalance = cadence
            s.strategy.top_n_per_group = top
            name = f"rotation_{profile}_{cadence}_stop{int(stop * 100)}_trail{0 if trail is None else 15}_top{top}"
            result[name] = s
        for cadence, stop in itertools.product(["weekly", "monthly"], [0.08, 0.15]):
            s = result[
                f"rotation_{profile}_{cadence}_stop{int(stop * 100)}_trail0_top2"
            ].model_copy(deep=True)
            s.strategy.name = "equal_weight"
            result[f"equal_{profile}_{cadence}_stop{int(stop * 100)}"] = s
    return result


class CachedData:
    def __init__(self, provider):
        self.provider = provider
        self.cache = {}

    def load(self, symbols, through=None):
        key = (tuple(symbols), through)
        if key not in self.cache:
            self.cache[key] = self.provider.load(symbols, through)
        return self.cache[key]


SIGNALS = {}


class CachedStrategy:
    def __init__(self, s):
        self.key = dumps(s.model_dump())
        self.engine = StrategyEngine(s)

    def targets(self, data, asof):
        key = (self.key, str(asof))
        if key not in SIGNALS:
            SIGNALS[key] = self.engine.targets(data, asof)
        return SIGNALS[key]


def summary(name, result):
    m = result["metrics"]
    p = result["equity"]
    initial = result["initial"]
    return {
        "name": name,
        "start": result["start"],
        "end": result["end"],
        **m,
        "ending_equity": p[-1]["equity"],
        "pnl": p[-1]["equity"] - initial,
        "orders": len(result["orders"]),
        "halted": result["halted"],
        "SPY_return": p[-1]["SPY"] / initial - 1,
        "QQQ_return": p[-1]["QQQ"] / initial - 1,
        "data_hash": result["data_hash"],
    }


def evaluate(service, name, s, start, end, label):
    path = OUT / f"{label}_{name}.json"
    if path.exists():
        return json.loads(path.read_text())
    try:
        r = run_backtest(service, s, start, end)
        brief = summary(name, r)
        path.write_text(dumps(brief))
        if label.startswith(("test", "stress")):
            (OUT / f"{label}_{name}_detail.json").write_text(dumps(r))
        print(
            json.dumps(
                {
                    "stage": label,
                    "candidate": name,
                    "return": round(brief["total_return"], 4),
                    "drawdown": round(brief["max_drawdown"], 4),
                }
            ),
            flush=True,
        )
        return brief
    except Exception as e:  # noqa: BLE001 -- persist failed research trials and exclude them from selection
        error = {"name": name, "error": type(e).__name__ + ": " + str(e)}
        path.write_text(dumps(error))
        print(dumps(error), flush=True)
        return error


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.mkdir(parents=True, exist_ok=True)
    all_configs = configs()
    (OUT / "protocol.json").write_text(dumps(PROTOCOL))
    (OUT / "candidates.json").write_text(
        dumps({k: v.model_dump() for k, v in all_configs.items()})
    )
    svc = SimpleNamespace(
        db=DB(STATE / "research.db"), data=CachedData(MarketData(STATE / "historical"))
    )
    leaderboard = []
    with patch("trader.backtest.StrategyEngine", CachedStrategy):
        for name, s in all_configs.items():
            folds = [
                evaluate(svc, name, s, *period, f"train{i}")
                for i, period in enumerate(PROTOCOL["training_folds"])
            ]
            if any("error" in f for f in folds):
                continue
            eligible = all(f["max_drawdown"] >= -0.20 for f in folds)
            score = math.prod(1 + f["total_return"] for f in folds) - 1
            leaderboard.append(
                {
                    "name": name,
                    "training_score": score,
                    "training_eligible": eligible,
                    "training_worst_drawdown": min(f["max_drawdown"] for f in folds),
                    "training_min_return": min(f["total_return"] for f in folds),
                }
            )
        leaderboard.sort(key=lambda r: r["training_score"], reverse=True)
        selected = [r["name"] for r in leaderboard if r["training_eligible"]][:8]
        if "baseline" not in selected:
            selected.append("baseline")
        validation = [
            evaluate(svc, n, all_configs[n], *PROTOCOL["validation"], "validation")
            for n in selected
        ]
        eligible = [
            r
            for r in validation
            if "error" not in r
            and r["max_drawdown"] >= -0.2
            and any(
                x["name"] == r["name"] and x["training_eligible"] for x in leaderboard
            )
        ]
        if not eligible:
            raise RuntimeError(
                "No configuration met training and validation risk constraints; no recommendation"
            )
        winner = max(eligible, key=lambda r: r["total_return"])["name"]
        frozen = {
            "selected": winner,
            "configuration": all_configs[winner].model_dump(),
            "selected_before_test": True,
            "protocol_sha256": hashlib.sha256(dumps(PROTOCOL).encode()).hexdigest(),
        }
        (OUT / "selection_locked.json").write_text(dumps(frozen))
        (OUT / "recommended_research_settings.json").write_text(
            dumps(all_configs[winner].model_dump())
        )
        pd.DataFrame(leaderboard).to_csv(OUT / "training_leaderboard.csv", index=False)
        pd.DataFrame(validation).to_csv(OUT / "validation.csv", index=False)
        test_old = [
            evaluate(
                svc,
                n,
                all_configs[n],
                *PROTOCOL["previously_seen_test"],
                "test_previous",
            )
            for n in dict.fromkeys([winner, "baseline"])
        ]
    # Refresh only after winner is locked; preserve downloaded bars to reproduce final evaluation.
    symbols = Settings().strategy.universe + REQUIRED
    fresh = MarketData(SNAPSHOT)
    if all(fresh.path(s).exists() for s in symbols):
        # Replay the frozen vendor snapshot without requesting revised history.
        download = {
            s: {"bars": len(df), "last": str(df.index[-1].date())}
            for s, df in fresh.load(symbols).items()
        }
    else:
        fetched = MarketData(STATE / "fresh")
        download = fetched.refresh(symbols)
        if not any("error" in r for r in download.values()):
            for s in symbols:
                path = fetched.path(s)
                shutil.copy2(path, fresh.path(s))
                shutil.copy2(
                    path.with_suffix(".json"), fresh.path(s).with_suffix(".json")
                )
    (OUT / "download_status.json").write_text(dumps(download))
    if any("error" in r for r in download.values()):
        raise RuntimeError("Fresh data unavailable; no synthetic replacement")
    if min(r["last"] for r in download.values()) < "2026-10-30":
        raise RuntimeError("Fresh data does not cover declared final date")
    svc.data = CachedData(fresh)
    SIGNALS.clear()
    with patch("trader.backtest.StrategyEngine", CachedStrategy):
        test_new = [
            evaluate(svc, n, all_configs[n], *PROTOCOL["fresh_test"], "test_fresh")
            for n in dict.fromkeys([winner, "baseline"])
        ]
        stress = []
        for i, cost in enumerate(PROTOCOL["stress_costs"]):
            s = all_configs[winner].model_copy(deep=True)
            for k, v in cost.items():
                setattr(s.simulation, k, v)
            stress.append(
                evaluate(svc, winner, s, *PROTOCOL["fresh_test"], f"stress{i}")
            )
    (OUT / "summary.json").write_text(
        dumps(
            {
                "selection": frozen,
                "training": leaderboard,
                "validation": validation,
                "test_previous": test_old,
                "test_fresh": test_new,
                "stress": stress,
            }
        )
    )
    print("COMPLETE " + winner, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT,
        help="Use a new directory to recompute rather than resume saved results.",
    )
    OUT = parser.parse_args().output
    main()
