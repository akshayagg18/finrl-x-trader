"""Run the BTC/ETH market-neutral relative-value research track."""

import json

from trader.growth.hedges import RELATIVE_VALUE_SPECS, simulate_relative_value

from .hedge_research_common import run_track


def main() -> None:
    summary = run_track(
        track="relative_value",
        title="BTC/ETH market-neutral relative-value research",
        script="scripts.evaluate_relative_value",
        specs=RELATIVE_VALUE_SPECS,
        simulator=simulate_relative_value,
        base_kwargs={"cost_bps": 15.0, "short_carry_annual": 0.10},
        stress_kwargs={"cost_bps": 30.0, "short_carry_annual": 0.20},
        mechanism=(
            "The strategy trades deviations in the lagged log BTC/ETH price ratio. "
            "It holds equal-notional long and short legs, scales gross exposure by "
            "ratio volatility, and exits as the ratio approaches its rolling mean."
        ),
        limitations=[
            "Market neutrality removes first-order direction, not basis or spread risk.",
            "Both legs use spot prices as derivative proxies.",
            "Base short carry is charged at 10% annualized and stressed to 20%.",
            "Cointegration is not assumed to persist outside the measured history.",
        ],
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
