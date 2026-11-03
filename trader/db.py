import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import Settings


def now():
    return datetime.now(timezone.utc).isoformat()


def dumps(value):
    def native(obj):
        if hasattr(obj, "item"):
            return obj.item()
        return str(obj)

    return json.dumps(value, default=native, allow_nan=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, applied TEXT);
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts(scope TEXT PRIMARY KEY, cash REAL NOT NULL, initial REAL NOT NULL, contributions REAL NOT NULL, peak REAL NOT NULL, baseline_equity REAL, broker_id TEXT);
CREATE TABLE IF NOT EXISTS positions(scope TEXT, symbol TEXT, qty REAL NOT NULL, cost REAL NOT NULL, peak REAL NOT NULL, PRIMARY KEY(scope,symbol));
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, scope TEXT NOT NULL, cycle TEXT NOT NULL, created TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, qty REAL NOT NULL, intended REAL NOT NULL, status TEXT NOT NULL, broker_id TEXT, filled_qty REAL NOT NULL DEFAULT 0, fill_price REAL, fees REAL NOT NULL DEFAULT 0, realized REAL NOT NULL DEFAULT 0, strategy TEXT, reason TEXT, risk TEXT);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, scope TEXT, kind TEXT, body TEXT);
CREATE TABLE IF NOT EXISTS equity(id INTEGER PRIMARY KEY AUTOINCREMENT, scope TEXT, date TEXT, equity REAL, cash REAL, flow REAL DEFAULT 0, UNIQUE(scope,date));
CREATE TABLE IF NOT EXISTS cycles(id TEXT PRIMARY KEY, scope TEXT, created TEXT, status TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS research(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, kind TEXT, config TEXT, result TEXT);
CREATE TABLE IF NOT EXISTS models(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, strategy TEXT, body TEXT, deployed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS llm_requests(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, cycle_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL, input_refs TEXT NOT NULL, request_hash TEXT NOT NULL, output TEXT NOT NULL, input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, cost_usd REAL NOT NULL, latency_ms REAL NOT NULL, status TEXT NOT NULL, cached INTEGER NOT NULL DEFAULT 0, request_id TEXT);
CREATE INDEX IF NOT EXISTS ix_llm_requests_hash ON llm_requests(request_hash,status);
CREATE TABLE IF NOT EXISTS news_events(id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT UNIQUE NOT NULL, publisher TEXT NOT NULL, source_url TEXT NOT NULL, published_at TEXT NOT NULL, updated_at TEXT, available_at TEXT NOT NULL, retrieved_at TEXT NOT NULL, assets TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, content_hash TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_news_available ON news_events(available_at);
CREATE TABLE IF NOT EXISTS llm_shadow(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, decision_time TEXT NOT NULL, variant TEXT NOT NULL, asset TEXT NOT NULL, baseline_action TEXT NOT NULL, llm_output TEXT, effective_action TEXT NOT NULL, settled_pnl REAL, status TEXT NOT NULL);
"""


class DB:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            tables = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='migrations'"
            ).fetchone()
            if (
                tables
                and (
                    c.execute("SELECT MAX(version) FROM migrations").fetchone()[0] or 0
                )
                > 1
            ):
                raise RuntimeError(
                    "Database schema is newer than this application; refusing downgrade"
                )
            c.executescript(SCHEMA)
            c.execute("INSERT OR IGNORE INTO migrations VALUES(1,?)", (now(),))
            if not c.execute("SELECT 1 FROM settings").fetchone():
                c.execute(
                    "INSERT INTO settings(created,body) VALUES(?,?)",
                    (now(), dumps(Settings().model_dump())),
                )

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def rows(self, sql, args=()):
        with self.connect() as c:
            return [dict(x) for x in c.execute(sql, args)]

    def settings(self):
        return Settings.model_validate_json(
            self.rows("SELECT body FROM settings ORDER BY id DESC LIMIT 1")[0]["body"]
        )

    def state(self, key, default=None):
        r = self.rows("SELECT value FROM state WHERE key=?", (key,))
        return json.loads(r[0]["value"]) if r else default

    def set_state(self, key, value):
        with self.connect() as c:
            c.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (key, dumps(value)))

    def event(self, scope, kind, body):
        with self.connect() as c:
            c.execute(
                "INSERT INTO events(created,scope,kind,body) VALUES(?,?,?,?)",
                (now(), scope, kind, dumps(body)),
            )

    def ensure_account(self, scope, capital):
        with self.connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO accounts(scope,cash,initial,contributions,peak) VALUES(?,?,?,?,?)",
                (scope, capital, capital, capital, capital),
            )

    def backup(self, target):
        with self.connect() as c, sqlite3.connect(target) as dest:
            c.backup(dest)
