"""Run the rolling synthetic protective-put research track."""

import json

from trader.growth.hedges import PUT_PROTECTION_SPECS, simulate_put_protection

from .hedge_research_common import run_track


def main() -> None:
    summary = run_track(
        track="put_protection",
        title="Long/cash strategy with synthetic protective puts",
        script="scripts.evaluate_put_protection",
        specs=PUT_PROTECTION_SPECS,
        simulator=simulate_put_protection,
        base_kwargs={"cost_bps": 15.0, "volatility_stress": 1.0},
        stress_kwargs={"cost_bps": 30.0, "volatility_stress": 1.25},
        mechanism=(
            "The existing weekly BTC-gated long allocation buys rolling BTC and "
            "ETH puts covering 50% or 100% of exposure. Puts are marked with "
            "Black-Scholes using lagged 30-day realized volatility plus a 25% markup."
        ),
        limitations=[
            "No historical option-chain quotes or volatility surface are available.",
            "Black-Scholes marks omit skew, jumps, exchange margin and quote depth.",
            "Stress doubles trading friction and raises modeled implied volatility 25%.",
            "These are synthetic insurance estimates, not executable option backtests.",
        ],
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
