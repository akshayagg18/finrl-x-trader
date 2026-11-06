import sqlite3

from scripts.backup_forward import backup
from scripts.forward_watchdog import run
from trader.db import DB
from trader.growth.defensive_forward import configure, control, status


def test_watchdog_respects_intentional_stop_and_global_kill(tmp_path):
    db = DB(tmp_path / "state.db")
    configure(db, {})
    control(db, "start")
    control(db, "stop")
    called = []
    stopped = run(db, tick_function=lambda _: called.append(True))
    assert not stopped["active"] and not called

    db.set_state("kill", True)
    with db.connect() as connection:
        connection.execute(
            "UPDATE defensive_forward SET active=0,error='ReadTimeout' WHERE id=1"
        )
    killed = run(db, tick_function=lambda _: called.append(True))
    assert not killed["active"] and killed["error"] == "ReadTimeout" and not called


def test_watchdog_retries_only_transient_failure(tmp_path):
    db = DB(tmp_path / "state.db")
    configure(db, {})
    with db.connect() as connection:
        connection.execute(
            "UPDATE defensive_forward SET active=0,error='ReadTimeout' WHERE id=1"
        )

    def successful_tick(target):
        return status(target)

    recovered = run(db, tick_function=successful_tick)
    assert recovered["active"] and recovered["error"] is None
    assert db.rows("SELECT 1 FROM events WHERE kind='watchdog_retry'")

    control(db, "stop")
    with db.connect() as connection:
        connection.execute(
            "UPDATE defensive_forward SET active=0,error='ValueError' WHERE id=1"
        )
    blocked = run(db, tick_function=lambda _: (_ for _ in ()).throw(AssertionError()))
    assert not blocked["active"] and blocked["error"] == "ValueError"


def test_forward_backup_is_consistent_and_rotates(tmp_path):
    source = tmp_path / "state.db"
    db = DB(source)
    configure(db, {})
    directory = tmp_path / "backups"
    first = backup(str(source), str(directory), keep=1)
    assert first.exists()
    with sqlite3.connect(first) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("SELECT COUNT(*) FROM defensive_forward").fetchone()[0] == 1
    renamed = directory / "forward-20000101T000000Z.db"
    first.rename(renamed)
    second = backup(str(source), str(directory), keep=1)
    assert second.exists() and not renamed.exists()
