"""Adapters call upstream weight generators, never replace their signals."""

import pandas as pd
from src.strategies.adaptive_rotation import AdaptiveRotationEngine
from src.strategies.adaptive_rotation.config_loader import load_config
from src.strategies.adaptive_rotation.intra_group_ranking import IntraGroupRanker
from src.strategies.base_strategy import EqualWeightStrategy, StrategyConfig
from .data import ROOT

CATALOG = [
    {
        "id": "adaptive_rotation",
        "name": "Adaptive Rotation",
        "status": "functional",
        "requirements": "26+ completed weeks, SPX/VIX/QQQ and selected group assets; no trained model",
        "cadence": "weekly + daily risk",
        "source": "src/strategies/adaptive_rotation",
    },
    {
        "id": "equal_weight",
        "name": "FinRL-X Equal Weight",
        "status": "functional",
        "requirements": "Price history; no training",
        "cadence": "configurable",
        "source": "src/strategies/base_strategy.py",
    },
    {
        "id": "rolling_ml",
        "name": "Rolling Stock Selection · RF / GBM / LGBM / XGB",
        "status": "research only",
        "requirements": "Point-in-time fundamentals, known label-availability dates, training. Upstream bundled fundamentals lack certified vintage provenance. Deployment blocked.",
        "source": "src/strategies/ml_strategy.py",
    },
    {
        "id": "drl",
        "name": "DRL · A2C / PPO / DDPG / TD3 / SAC",
        "status": "unavailable",
        "requirements": "FinRL environment dependency + trained model artifacts and validated observation schema; research script is not a deployable adapter",
        "source": "src/strategies/rl_model.py",
    },
    {
        "id": "ensemble",
        "name": "Published Rolling + Rotation ensemble",
        "status": "unavailable",
        "requirements": "Exact deployed ensemble combiner, artifacts, weights and data not supplied by upstream; +19.76% is not this installation’s result",
        "source": "upstream README",
    },
]


class DailyView:
    def __init__(self, data):
        self.data = data

    def get_daily_data_as_of(self, as_of_date, symbols):
        return {
            s: self.data[s].loc[:as_of_date, "close"] for s in symbols if s in self.data
        }


class StrategyEngine:
    def __init__(self, settings):
        self.settings = settings
        cfg = load_config(
            str(
                ROOT
                / f"src/strategies/AdaptiveRotationConf_{settings.rotation_version}.yaml"
            )
        )
        for key in list(cfg.asset_groups):
            subset = [
                s for s in cfg.asset_groups[key].symbols if s in settings.universe
            ]
            if subset:
                cfg.asset_groups[key].symbols = subset
            else:
                del cfg.asset_groups[key]
        cfg.ranking.top_n_per_group = settings.top_n_per_group
        self.rotation = AdaptiveRotationEngine(cfg)
        # Upstream passes top_n as lookback; use declared ranking window instead.
        self.rotation.intra_group_ranker = IntraGroupRanker(
            lookback_weeks=cfg.ranking.zscore_window or 12, robust=cfg.ranking.robust
        )

    def targets(self, data, asof):
        asof = pd.Timestamp(asof)
        if self.settings.name == "equal_weight":
            result = EqualWeightStrategy(
                StrategyConfig(name="equal_weight")
            ).generate_weights(
                {"fundamentals": pd.DataFrame({"gvkey": self.settings.universe})}
            )
            return dict(zip(result.weights.gvkey, result.weights.weight)), {
                "source": "upstream EqualWeightStrategy",
                "asof": str(asof),
            }
        if self.settings.name != "adaptive_rotation":
            raise ValueError(
                "ML/DRL deployment blocked until point-in-time data and model validation are supplied"
            )
        daily = {s: df.loc[:asof] for s, df in data.items()}
        self.rotation.data_preprocessor = DailyView(daily)
        # Exclude partial weeks: resample only data available at asof, then trim labels after asof.
        weekly = {
            s: df.close.resample("W-FRI").last().loc[:asof].dropna()
            for s, df in daily.items()
        }
        if any(len(s) < 26 for s in weekly.values()):
            raise ValueError("Adaptive Rotation requires 26 completed weekly bars")
        weights, audit = self.rotation.run(weekly, asof, mode="backtest")
        return weights.weights, audit.to_dict()
