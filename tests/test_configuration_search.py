from types import SimpleNamespace
from unittest.mock import patch

from scripts.search_configurations import (
    PROTOCOL,
    SIGNALS,
    CachedData,
    CachedStrategy,
    configs,
)
from trader.backtest import run_backtest
from trader.config import Settings
from trader.data import MarketData
from trader.db import DB


def test_candidates_are_valid_and_keep_universe_fixed():
    candidates = configs()
    assert len(candidates) == 61
    for s in candidates.values():
        Settings.model_validate(s.model_dump())
        assert s.capital.allocated == 500
        assert s.strategy.universe == Settings().strategy.universe
        assert s.broker.mode == "simulation"
        assert s.capital.deployment + s.capital.cash_reserve <= 1.000001
    assert PROTOCOL["validation"][1] < PROTOCOL["fresh_test"][0]


def test_cached_upstream_signals_match_real_backtest(tmp_path):
    service = SimpleNamespace(
        db=DB(tmp_path / "research.db"),
        data=CachedData(MarketData(tmp_path / "prices")),
    )
    settings = Settings()
    expected = run_backtest(service, settings, "2022-01-03", "2022-01-31")
    SIGNALS.clear()
    with patch("trader.backtest.StrategyEngine", CachedStrategy):
        actual = run_backtest(service, settings, "2022-01-03", "2022-01-31")
    assert actual["equity"] == expected["equity"]
    assert actual["orders"] == expected["orders"]
    assert actual["metrics"] == expected["metrics"]
