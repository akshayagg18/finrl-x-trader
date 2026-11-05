import hashlib
import json
from pathlib import Path

import pytest

from trader.db import dumps
from trader.growth.defensive import DefensiveRisk
from trader.growth.hedges import (
    PUT_PROTECTION_SPECS,
    RELATIVE_VALUE_SPECS,
    SHORT_HEDGE_SPECS,
    PutProtectionSpec,
    RelativeValueSpec,
    ShortHedgeSpec,
    put_price,
    simulate_put_protection,
    simulate_relative_value,
    simulate_short_hedge,
)
from trader.growth.regime import load_long_history


@pytest.fixture(scope="module")
def long_data():
    return {
        symbol: load_long_history(symbol)
        for symbol in ("BTC-USDT", "ETH-USDT")
    }


def test_research_grids_are_fixed_and_distinct():
    assert len(SHORT_HEDGE_SPECS) == 81
    assert len(RELATIVE_VALUE_SPECS) == 96
    assert len(PUT_PROTECTION_SPECS) == 108
    assert len({spec.name for spec in SHORT_HEDGE_SPECS}) == 81
    assert len({spec.name for spec in RELATIVE_VALUE_SPECS}) == 96
    assert len({spec.name for spec in PUT_PROTECTION_SPECS}) == 108


def test_synthetic_put_price_has_intrinsic_floor_and_time_value():
    assert put_price(100, 110, 0, 0.5) == 10
    assert put_price(100, 100, 30 / 365, 0.5) > 0
    with pytest.raises(ValueError):
        put_price(0, 100, 1, 0.5)


def test_short_hedge_is_bounded_and_carry_reduces_equity(long_data):
    spec = ShortHedgeSpec(100, 90, 0.25, "either")
    risk = DefensiveRisk(0.10, 0.20, 0.30)
    free = simulate_short_hedge(
        long_data,
        spec,
        "2022-01-01",
        "2022-12-31",
        risk=risk,
        short_carry_annual=0,
    )
    charged = simulate_short_hedge(
        long_data,
        spec,
        "2022-01-01",
        "2022-12-31",
        risk=risk,
        short_carry_annual=0.20,
    )
    assert any(
        decision["weights"]["BTC-USDT"] < 0
        for decision in charged["decisions"]
    )
    assert max(item["gross_exposure"] for item in charged["decisions"]) <= 0.2
    assert charged["financing_costs"] > 0
    assert charged["ending_equity"] < free["ending_equity"]


def test_relative_value_is_equal_notional_and_bounded(long_data):
    result = simulate_relative_value(
        long_data,
        RelativeValueSpec(60, 2.0, 0.0, "weekly", 0.30),
        "2024-01-01",
        "2024-12-31",
        risk=DefensiveRisk(0.10, 0.20, 0.30),
    )
    active = [
        decision
        for decision in result["decisions"]
        if decision["gross_exposure"] > 0
    ]
    assert active
    for decision in active:
        assert sum(decision["weights"].values()) == pytest.approx(0)
        assert decision["gross_exposure"] <= 0.2
    assert result["financing_costs"] > 0


def test_put_protection_is_funded_and_marked_nonnegative(long_data):
    result = simulate_put_protection(
        long_data,
        PutProtectionSpec(100, 90, 0.15, 0.50, 28),
        "2024-01-01",
        "2024-06-30",
        risk=DefensiveRisk(0.10, 0.20, 0.30),
    )
    assert result["premium_paid"] > 0
    assert result["option_sale_value"] > 0
    assert min(point["option_value"] for point in result["points"]) >= 0
    assert min(point["cash"] for point in result["points"]) >= -1e-9


def test_locked_hedge_track_results_are_honest():
    expectations = {
        "short_hedge": set(),
        "relative_value": set(),
        "put_protection": {"drawdown_10"},
    }
    for track, profitable_tiers in expectations.items():
        root = Path("research") / track
        protocol = json.loads((root / "protocol.json").read_text())
        lock = json.loads((root / "selection_locked.json").read_text())
        summary = json.loads((root / "summary.json").read_text())
        assert hashlib.sha256(dumps(protocol).encode()).hexdigest() == lock[
            "protocol_sha256"
        ]
        actual = {
            name
            for name, tier in summary["tiers"].items()
            if tier["historically_profitable"]
        }
        assert actual == profitable_tiers
        assert not any(
            tier["deployment_qualified"] for tier in summary["tiers"].values()
        )


def test_four_track_comparison_retains_long_cash_and_blocks_deployment():
    comparison = json.loads(
        Path("research/hedge_comparison/summary.json").read_text()
    )
    assert set(comparison["tracks"]) == {
        "long_cash",
        "short_hedge",
        "relative_value",
        "put_protection",
    }
    assert set(comparison["preferred_historical_track"].values()) == {
        "long_cash"
    }
    assert not comparison["deployment_qualified"]
