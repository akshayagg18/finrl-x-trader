import os
import json
import csv
import io
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from .service import Service
from .config import Settings, PRESETS
from .db import now, dumps
from .strategies import CATALOG
from .brokers import create_broker, MissingCredentials
from .scheduler import Scheduler
from .backtest import run_backtest

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]


def create_app(path=None, with_scheduler=True):
    service = Service(path or os.getenv("TRADER_DB", str(ROOT / "runtime/trader.db")))
    scheduler = Scheduler(service)

    @asynccontextmanager
    async def lifespan(app):
        if with_scheduler:
            scheduler.start()
        yield
        scheduler.stop()

    app = FastAPI(title="FinRL-X Trading Console", lifespan=lifespan)
    app.state.service = service
    # Optional research engine; the original console starts without its extra dependencies.
    try:
        from .intraday.api import router as intraday_router
    except ModuleNotFoundError as exc:
        if not exc.name.startswith("nautilus_trader"):
            raise
    else:
        app.include_router(intraday_router(service.db))

    @app.middleware("http")
    async def local_guard(request: Request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in ("127.0.0.1", "localhost", "testserver", "[", "::1"):
            return JSONResponse(
                {
                    "detail": "Local access only. Configure a private authenticated reverse proxy deliberately."
                },
                status_code=403,
            )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if origin and origin not in (
                "http://" + request.headers.get("host", ""),
                "https://" + request.headers.get("host", ""),
            ):
                return JSONResponse(
                    {"detail": "Cross-origin mutation denied"}, status_code=403
                )
            if request.headers.get("x-trader-intent") != "console":
                return JSONResponse(
                    {"detail": "X-Trader-Intent header required"}, status_code=403
                )
        try:
            r = await call_next(request)
        except Exception as exc:
            from .risk import RiskBlocked
            from .data import DataError

            safe = (
                str(exc)
                if isinstance(exc, (RiskBlocked, DataError))
                else type(exc).__name__
            )
            service.db.event(
                service.scope(), "api_error", {"path": request.url.path, "error": safe}
            )
            r = JSONResponse({"detail": safe}, status_code=400)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["Referrer-Policy"] = "no-referrer"
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
        )
        return r

    @app.exception_handler(Exception)
    async def error_handler(request, exc):
        from .risk import RiskBlocked
        from .data import DataError

        safe = (
            str(exc)
            if isinstance(exc, (RiskBlocked, DataError))
            else type(exc).__name__
        )
        service.db.event(
            service.scope(), "api_error", {"path": request.url.path, "error": safe}
        )
        return JSONResponse({"detail": safe}, status_code=400)

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "live_default": "disabled",
            "schema": 1,
            "upstream": "4409abe925c904e570be78ebfb5e77ac3491dff8",
        }

    @app.get("/api/overview")
    def overview():
        return service.overview()

    @app.get("/api/settings")
    def settings():
        return {
            "settings": service.db.settings().model_dump(),
            "presets": PRESETS,
            "schema": Settings.model_json_schema(),
            "versions": service.db.rows(
                "SELECT id,created FROM settings ORDER BY id DESC LIMIT 30"
            ),
        }

    @app.put("/api/settings")
    def put_settings(s: Settings):
        return service.update_settings(s.model_dump()).model_dump()

    @app.get("/api/strategies")
    def strategies():
        return {
            "strategies": CATALOG,
            "models": service.db.rows("SELECT * FROM models ORDER BY id DESC"),
            "results": service.db.rows(
                "SELECT id,created,kind,config FROM research WHERE kind='backtest' ORDER BY id DESC"
            ),
        }

    @app.get("/api/data")
    def inventory():
        return service.data.inventory()

    @app.post("/api/data/refresh")
    def refresh():
        from .data import REQUIRED

        s = service.db.settings()
        result = service.data.refresh(
            s.strategy.universe + REQUIRED, s.data.timeout_seconds
        )
        service.db.event(service.scope(), "data_refresh", result)
        return result

    @app.post("/api/cycle")
    def cycle(body: dict):
        return JSONResponse(
            json.loads(
                dumps(
                    service.cycle(
                        dry_run=bool(body.get("dry_run", False)),
                        replay_date=body.get("replay_date"),
                    )
                )
            )
        )

    @app.post("/api/control/{action}")
    def control(action: str):
        return service.control(action)

    @app.post("/api/liquidate")
    def liquidate(body: dict):
        if body.get("confirm") != "LIQUIDATE BOT POSITIONS":
            raise HTTPException(400, "Explicit liquidation phrase required")
        return service.cycle(liquidate=True, replay_date=body.get("replay_date"))

    @app.post("/api/activate-live")
    def activate(body: dict):
        service.activate_live(body.get("phrase"))
        return {"activated": True}

    @app.post("/api/broker/test")
    def broker_test():
        s = service.db.settings()
        scope = service.scope()
        if s.broker.broker == "local":
            result = {
                "status": "ready",
                "account": scope,
                "capabilities": [
                    "fractional shares",
                    "deterministic fills",
                    "persisted cash and holdings",
                ],
            }
        else:
            try:
                b = create_broker(s.broker)
                a = b.account()
                result = {
                    "status": "connected",
                    "account": a.id,
                    "cash": a.cash,
                    "equity": a.equity,
                    "blocked": a.blocked,
                    "market_open": b.market_open(),
                    "capabilities": [
                        "market DAY",
                        "fractional eligible assets"
                        if s.broker.broker == "alpaca"
                        else "whole shares; external session verification required",
                    ],
                    "execution_ready": False,
                    "note": "Connection test is read-only; identity, dedicated ownership, activation and final risk checks still required.",
                }
            except Exception as exc:
                result = {
                    "status": "unavailable",
                    "reason": str(exc)
                    if isinstance(exc, MissingCredentials)
                    else type(exc).__name__,
                }
        result["checked_at"] = now()
        service.db.set_state("connection:" + scope, result)
        return result

    @app.post("/api/backtests")
    def backtest(body: dict):
        s = Settings.model_validate(
            body.get("settings", service.db.settings().model_dump())
        )
        return JSONResponse(
            json.loads(
                dumps(
                    run_backtest(
                        service,
                        s,
                        body.get("start", "2025-01-02"),
                        body.get("end", "2025-10-07"),
                        body.get("oos_start"),
                    )
                )
            )
        )

    @app.get("/api/research/{rid}")
    def research(rid: int):
        rows = service.db.rows("SELECT * FROM research WHERE id=?", (rid,))
        if not rows:
            raise HTTPException(404, "Result absent")
        return {
            **rows[0],
            "config": json.loads(rows[0]["config"]),
            "result": json.loads(rows[0]["result"]),
        }

    @app.post("/api/models/train-ml")
    def train_ml(body: dict):
        from .research_ml import train

        return JSONResponse(
            json.loads(
                dumps(
                    train(
                        service,
                        body.get("asof", "2025-06-02"),
                        int(body.get("test_quarters", 4)),
                    )
                )
            )
        )

    @app.post("/api/models/snapshot")
    def snapshot():
        s = service.db.settings()
        if s.strategy.name not in ("adaptive_rotation", "equal_weight"):
            raise HTTPException(400, "Model training dependencies/data not verified")
        with service.db.connect() as c:
            r = c.execute(
                "INSERT INTO models(created,strategy,body) VALUES(?,?,?)",
                (now(), s.strategy.name, dumps(s.strategy.model_dump())),
            )
        return {
            "id": r.lastrowid,
            "note": "Deterministic strategy configuration snapshot; no training required or claimed",
        }

    @app.post("/api/models/{mid}/deploy")
    def deploy(mid: int):
        rows = service.db.rows("SELECT * FROM models WHERE id=?", (mid,))
        if not rows:
            raise HTTPException(404, "Model absent")
        if rows[0]["strategy"] not in ("adaptive_rotation", "equal_weight"):
            raise HTTPException(400, "Research ML/DRL deployment is not verified")
        s = service.db.settings().model_dump()
        s["strategy"] = json.loads(rows[0]["body"])
        s["strategy"]["model_version"] = mid
        service.update_settings(s)
        with service.db.connect() as c:
            c.execute("UPDATE models SET deployed=0")
            c.execute("UPDATE models SET deployed=1 WHERE id=?", (mid,))
        return {"deployed": mid, "automation": "stopped; start to apply"}

    @app.get("/api/events")
    def events():
        return service.db.rows("SELECT * FROM events ORDER BY id DESC LIMIT 500")

    @app.get("/api/export/{kind}")
    def export(kind: str, research_id: int | None = None):
        if kind == "research":
            rows = service.db.rows("SELECT * FROM research ORDER BY id")
        elif kind == "events":
            rows = service.db.rows("SELECT * FROM events ORDER BY id")
        elif kind in ("orders", "equity"):
            if research_id:
                r = research(research_id)["result"]
                rows = r["orders" if kind == "orders" else "equity"]
            else:
                rows = service.db.rows(
                    f"SELECT * FROM {kind} WHERE scope=?", (service.scope(),)
                )
        else:
            raise HTTPException(404, "Unknown export")
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]) if rows else ["empty"])
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{kind}.csv"'},
        )

    @app.post("/api/backup")
    def backup():
        dest = (
            Path(service.db.path).parent
            / "backups"
            / ("trader-" + now().replace(":", "-") + ".db")
        )
        dest.parent.mkdir(exist_ok=True)
        service.db.backup(dest)
        return {"file": dest.name}

    @app.get("/vendor/plotly.js")
    def plotly():
        import plotly

        return FileResponse(
            Path(plotly.__file__).parent / "package_data/plotly.min.js",
            media_type="application/javascript",
        )

    app.mount("/static", StaticFiles(directory=ROOT / "trader/static"), name="static")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "trader/static/index.html")

    return app


app = create_app()
