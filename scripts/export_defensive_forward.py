"""Export the public-data defensive forward-paper record without private state."""

import argparse
import json
from pathlib import Path

from trader.db import DB
from trader.growth.defensive_forward import status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/trader.db")
    parser.add_argument(
        "--output", default="research/defensive_forward/initial_observation.json"
    )
    args = parser.parse_args()
    db = DB(args.db)
    state = status(db)
    if not state.get("configured") or not state.get("observations"):
        raise ValueError("No defensive forward observation to export")
    observations = [
        {
            "day": row["day"],
            "received": row["received"],
            "body": json.loads(row["body"]),
        }
        for row in db.rows(
            "SELECT day,received,body FROM defensive_forward_observations ORDER BY day"
        )
    ]
    payload = {
        "mode": state["mode"],
        "candidate": state["candidate"],
        "risk": state["risk"],
        "config": state["config"],
        "observations": observations,
        "result": state["result"],
        "qualification": state["qualification"],
        "live_orders_possible": False,
        "broker_orders_submitted": 0,
        "boundary": (
            "Public-data local simulation only; this export is not broker paper "
            "or real-money performance"
        ),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
