"""Configure, start, and collect one defensive forward-paper observation."""

import argparse
import json

from trader.db import DB
from trader.growth.defensive_forward import configure, control, status, tick


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/trader.db")
    parser.add_argument("--capital", type=float, default=500.0)
    parser.add_argument(
        "--defer-observation",
        action="store_true",
        help="Activate persistent state and let the application scheduler observe",
    )
    args = parser.parse_args()
    db = DB(args.db)
    state = status(db)
    if not state["configured"]:
        configure(db, {"capital": args.capital})
    control(db, "start")
    print(json.dumps(status(db) if args.defer_observation else tick(db), indent=2))


if __name__ == "__main__":
    main()
