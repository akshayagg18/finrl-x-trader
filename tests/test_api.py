from fastapi.testclient import TestClient
from trader.api import create_app

HEAD = {"X-Trader-Intent": "console"}


def test_api_full_workflow(tmp_path):
    path = tmp_path / "api.db"
    with TestClient(
        create_app(path, with_scheduler=False), raise_server_exceptions=False
    ) as c:
        assert c.get("/").status_code == 200
        assert c.get("/api/health").json()["status"] == "ok"
        s = c.get("/api/settings").json()["settings"]
        s["risk"]["max_order"] = 75
        assert c.put("/api/settings", json=s, headers=HEAD).status_code == 200
        assert (
            c.post(
                "/api/cycle", headers=HEAD, json={"replay_date": "2025-01-06"}
            ).status_code
            == 200
        )
        assert c.get("/api/overview").json()["orders"]
        assert c.get("/api/export/orders").text.startswith("id,scope,cycle")
        assert c.post("/api/backup", headers=HEAD, json={}).status_code == 200
        assert (
            c.post(
                "/api/activate-live",
                headers=HEAD,
                json={"phrase": "ENABLE LIVE TRADING"},
            ).status_code
            == 400
        )
    with TestClient(create_app(path, False)) as c:
        assert c.get("/api/settings").json()["settings"]["risk"]["max_order"] == 75


def test_origin_and_host_security(tmp_path):
    with TestClient(create_app(tmp_path / "api.db", False)) as c:
        assert c.post("/api/control/start", json={}).status_code == 403
        assert (
            c.post(
                "/api/control/start",
                headers={**HEAD, "Origin": "https://malicious.example"},
                json={},
            ).status_code
            == 403
        )
        assert (
            c.get("/api/overview", headers={"Host": "malicious.example"}).status_code
            == 403
        )
        assert (
            c.get("/api/settings").json()["settings"]["broker"]["mode"] == "simulation"
        )


def test_api_does_not_leak_sdk_error(tmp_path, monkeypatch):
    app = create_app(tmp_path / "safe.db", False)

    def secret_error(**kw):
        raise RuntimeError("SECRET_MUST_NOT_LEAK")

    monkeypatch.setattr(app.state.service, "cycle", secret_error)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/api/cycle", json={}, headers=HEAD)
        assert r.status_code == 400 and "SECRET_MUST_NOT_LEAK" not in r.text
        assert "SECRET_MUST_NOT_LEAK" not in c.get("/api/events").text


def test_ml_training_saves_research_artifact(tmp_path):
    from trader.research_ml import train
    from trader.service import Service

    service = Service(tmp_path / "ml.db")
    r = train(service, "2025-06-02")
    assert r["metadata"]["model_name"] in ("rf", "gbm", "xgb", "lgbm")
    assert r["predictions"] and r["features"] and r["status"] == "research only"
    assert (tmp_path / "models" / f"ml-{r['id']}.joblib").exists()
    assert all("trade_price" != key for key in r["features"])
    assert sum(x["weight"] for x in r["targets"]) <= 1.00001
    with TestClient(create_app(tmp_path / "ml.db", False)) as c:
        assert (
            c.post(f"/api/models/{r['id']}/deploy", headers=HEAD, json={}).status_code
            == 400
        )
