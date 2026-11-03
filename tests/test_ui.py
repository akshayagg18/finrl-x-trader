"""Real Chromium E2E, isolated SQLite, actual historical data and strategy."""

import threading
import socket
import time
import pytest
import uvicorn
from playwright.sync_api import sync_playwright
from trader.api import create_app


@pytest.fixture
def browser_app(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app = create_app(tmp_path / "ui.db", with_scheduler=False)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for i in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started
    yield f"http://127.0.0.1:{port}", app.state.service
    server.should_exit = True
    thread.join(5)


def test_configuration_simulation_backtest_ui(browser_app, tmp_path):
    url, service = browser_app
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1050})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.wait_for_function(
            "document.querySelector('#equity').textContent.includes('500')"
        )
        page.locator('[data-page="settings"]').click()
        page.locator('[data-tab="capital"]').click()
        assert page.locator('[data-field="capital.allocated"]').input_value() == "500"
        page.locator('[data-tab="risk"]').click()
        page.locator('[data-field="risk.max_order"]').fill("75")
        page.locator('[data-field="risk.max_order"]').press("Tab")
        page.locator("#save-settings").click()
        page.wait_for_function(
            "document.querySelector('#notice').textContent.includes('Settings validated')"
        )
        assert service.db.settings().risk.max_order == 75
        page.reload()
        page.wait_for_function(
            "document.querySelector('#equity').textContent.includes('500')"
        )
        page.locator("#run-cycle").click()
        page.wait_for_function(
            "document.querySelector('#cycle-result').textContent.includes('filled')",
            timeout=60000,
        )
        assert service.overview()["orders"] and service.overview()["positions"]
        page.locator('[data-page="orders"]').click()
        assert page.locator("#orders-table tbody tr").count() > 0
        page.locator("#order-search").fill("AMZN")
        assert page.locator("#orders-table tbody").inner_text().count("AMZN") > 0
        page.locator('[data-page="research"]').click()
        page.locator("#bt-end").fill("2025-02-28")
        page.locator("#bt-oos").fill("2025-02-03")
        page.locator("#backtest").click()
        page.wait_for_function(
            "!document.querySelector('#bt-result').hidden", timeout=90000
        )
        assert page.locator("#bt-metrics").inner_text().find("Total return") >= 0
        assert service.db.rows("SELECT * FROM research")
        page.locator('[data-page="overview"]').click()
        page.screenshot(path=str(tmp_path / "dashboard.png"), full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(tmp_path / "mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()


def test_intraday_lab_persistence(browser_app):
    url, service = browser_app
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(url)
        page.wait_for_function(
            "document.querySelector('#in-allocation').value === '0.5'"
        )
        page.locator('[data-page="research"]').click()
        page.locator("#in-symbol").select_option("AAPL")
        page.locator("#in-strategy").select_option("hold")
        page.locator("#in-allocation").fill("0.8")
        page.locator("#in-run").click()
        page.wait_for_function(
            "document.querySelector('#in-result').textContent.includes('ending_equity')"
        )
        assert len(service.db.state("intraday_runs")[0]["fills"]) == 2
        page.reload()
        page.wait_for_function("document.querySelector('#in-symbol').value === 'AAPL'")
        assert service.db.state("intraday_settings")["allocation"] == 0.8
        browser.close()


def test_intraday_continuous_replay_ui(browser_app):
    url, service = browser_app
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page()
        page.goto(url)
        page.wait_for_function(
            "document.querySelector('#in-allocation').value === '0.5'"
        )
        ids = page.locator("[id]").evaluate_all("els=>els.map(e=>e.id)")
        assert len(ids) == len(set(ids))
        page.locator('[data-page="research"]').click()
        page.locator("#in-symbol").select_option("AAPL")
        page.locator("#in-strategy").select_option("hold")
        page.locator("#in-allocation").fill("0.8")
        page.locator("#in-create").click()
        page.wait_for_function(
            "document.querySelector('#in-session').textContent.includes('local historical simulation')"
        )
        page.locator("#in-replay-start").click()
        page.wait_for_function(
            "document.querySelector('#in-session').textContent.includes('\"active\": true')"
        )
        page.locator("#in-step").click()
        page.wait_for_function(
            "document.querySelector('#in-session').textContent.includes('\"quantity\": 1')"
        )
        page.reload()
        page.locator('[data-page="research"]').click()
        page.wait_for_function(
            "document.querySelector('#in-session').textContent.includes('\"quantity\": 1')"
        )
        assert len(service.db.rows("SELECT * FROM intraday_fills")) == 1
        page.locator("#in-liquidate").click()
        page.locator("#in-step").click()
        page.wait_for_function(
            "document.querySelector('#in-session').textContent.includes('\"quantity\": 0')"
        )
        assert len(service.db.rows("SELECT * FROM intraday_fills")) == 2
        browser.close()
