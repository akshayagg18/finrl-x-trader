"""Small monitoring command for the selected 12-week forward-paper account."""

import argparse
import json

from trader.db import DB
from trader.growth.defensive_forward import status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/trader.db")
    args = parser.parse_args()
    state = status(DB(args.db))
    result = state.get("result") or {}
    output = {
        "mode": state.get("mode"),
        "candidate": state.get("candidate"),
        "configured": state.get("configured"),
        "active": state.get("active"),
        "observations": state.get("observations", 0),
        "decision_weeks": state.get("decision_weeks", 0),
        "ending_equity": result.get("ending_equity"),
        "net_return": result.get("net_return"),
        "max_drawdown": result.get("max_drawdown"),
        "next_observation": state.get("next_observation"),
        "error": state.get("error"),
        "qualification": state.get("qualification"),
        "live_orders_possible": state.get("live_orders_possible", False),
    }
    print(json.dumps(output, indent=2))
    if not output["configured"] or not output["active"] or output["error"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
