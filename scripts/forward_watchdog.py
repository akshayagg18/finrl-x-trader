"""Retry transient public-data failures without overriding an intentional stop."""

import argparse
import json

from trader.db import DB
from trader.growth.defensive_forward import configure, control, status, tick

RECOVERABLE_ERRORS = {
    "ConnectionError",
    "ConnectTimeout",
    "HTTPError",
    "ReadTimeout",
    "Timeout",
    "TimeoutError",
}


def run(db: DB, *, tick_function=tick, capital: float = 500.0) -> dict:
    state = status(db)
    if not state["configured"]:
        configure(db, {"capital": capital})
        control(db, "start")
        return tick_function(db)
    if state["active"]:
        return tick_function(db)
    if state.get("error") in RECOVERABLE_ERRORS and not db.state("kill", False):
        db.event(
            "defensive_forward",
            "watchdog_retry",
            {"previous_error": state["error"]},
        )
        control(db, "start")
        return tick_function(db)
    # active=False/error=None is an intentional Stop. Global kill and data or
    # calculation errors also remain stopped for explicit inspection.
    return state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/trader.db")
    parser.add_argument("--capital", type=float, default=500.0)
    args = parser.parse_args()
    result = run(DB(args.db), capital=args.capital)
    print(
        json.dumps(
            {
                "configured": result.get("configured"),
                "active": result.get("active"),
                "observations": result.get("observations", 0),
                "decision_weeks": result.get("decision_weeks", 0),
                "error": result.get("error"),
                "live_orders_possible": result.get("live_orders_possible", False),
            },
            indent=2,
        )
    )
    if result.get("error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
