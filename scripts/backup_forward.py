"""Create a consistent SQLite forward-paper backup and rotate old copies."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trader.db import DB


def backup(db_path: str, directory: str, keep: int = 30) -> Path:
    if keep < 1:
        raise ValueError("keep must be positive")
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = destination / f"forward-{stamp}.db"
    DB(db_path).backup(target)
    copies = sorted(destination.glob("forward-*.db"), reverse=True)
    for old in copies[keep:]:
        old.unlink()
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="runtime/trader.db")
    parser.add_argument("--directory", default="runtime/backups")
    parser.add_argument("--keep", type=int, default=30)
    args = parser.parse_args()
    print(backup(args.db, args.directory, args.keep))


if __name__ == "__main__":
    main()
