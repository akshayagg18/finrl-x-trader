import argparse
import os
from pathlib import Path
from dotenv import load_dotenv
from .data import ROOT
from .service import Service
from .db import dumps


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description="FinRL-X self-hosted operations")
    parser.add_argument(
        "--db", default=os.getenv("TRADER_DB", str(ROOT / "runtime/trader.db"))
    )
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    p = sub.add_parser("serve")
    p.add_argument("--port", type=int, default=8765)
    p = sub.add_parser("simulate")
    p.add_argument("--date", default="2025-01-06")
    p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("backtest")
    p.add_argument("--start", default="2025-01-02")
    p.add_argument("--end", default="2025-10-07")
    p.add_argument("--oos-start", default="2025-07-01")
    p = sub.add_parser("backup")
    p.add_argument("destination")
    p = sub.add_parser("restore")
    p.add_argument("source")
    args = parser.parse_args()
    if args.action == "serve":
        os.environ["TRADER_DB"] = args.db
        import uvicorn

        uvicorn.run("trader.api:app", host="127.0.0.1", port=args.port, workers=1)
        return
    if args.action == "restore":
        import sqlite3

        source = Path(args.source)
        if not source.is_file():
            raise SystemExit("Backup does not exist")
        if Path(args.db).exists():
            raise SystemExit(
                "Restore to a new database path, then select TRADER_DB. Stop running services first."
            )
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src:
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SystemExit("Invalid backup")
            Path(args.db).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(args.db) as dest:
                src.backup(dest)
        db = Service(args.db).db
        db.set_state("automation", False)
        db.set_state("live_activation", None)
        db.set_state("kill", True)
        print(
            "Restored with kill enabled and live activation revoked. Reconcile before reset."
        )
        return
    service = Service(args.db)
    if args.action == "init":
        output = service.db.settings().model_dump()
        path = Path(args.db).parent / "settings.example.json"
        path.write_text(dumps(output))
        print(f"Initialized {args.db}. Template: {path}. Live disabled.")
    elif args.action == "status":
        print(dumps(service.overview()))
    elif args.action == "simulate":
        print(dumps(service.cycle(replay_date=args.date, dry_run=args.dry_run)))
    elif args.action == "backtest":
        from .backtest import run_backtest

        r = run_backtest(
            service, service.db.settings(), args.start, args.end, args.oos_start
        )
        print(
            dumps(
                {
                    "research_id": r["id"],
                    "metrics": r["metrics"],
                    "orders": len(r["orders"]),
                    "halted": r["halted"],
                }
            )
        )
    elif args.action == "backup":
        service.db.backup(args.destination)
        print("Backup created")


if __name__ == "__main__":
    main()
