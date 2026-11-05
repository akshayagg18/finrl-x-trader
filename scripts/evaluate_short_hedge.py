"""Run the BTC short-hedge research track."""

import json

from trader.growth.hedges import SHORT_HEDGE_SPECS, simulate_short_hedge

from .hedge_research_common import run_track


def main() -> None:
    summary = run_track(
        track="short_hedge",
        title="Long/cash strategy with a BTC short hedge",
        script="scripts.evaluate_short_hedge",
        specs=SHORT_HEDGE_SPECS,
        simulator=simulate_short_hedge,
        base_kwargs={"cost_bps": 15.0, "short_carry_annual": 0.10},
        stress_kwargs={"cost_bps": 30.0, "short_carry_annual": 0.20},
        mechanism=(
            "The strategy keeps the existing weekly BTC-gated BTC/ETH long "
            "allocation in positive regimes. In negative regimes it may hold a "
            "BTC short sized to 25%, 50%, or 100% of the tier exposure limit."
        ),
        limitations=[
            "The short is modeled from spot prices; no futures order book is available.",
            "Base short carry is charged at 10% annualized and stressed to 20%.",
            "Liquidation, margin calls, funding sign changes and basis are not observed.",
        ],
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
