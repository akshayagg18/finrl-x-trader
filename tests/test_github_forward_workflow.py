from pathlib import Path


def test_daily_forward_workflow_is_paper_only_and_persistent():
    workflow = Path(".github/workflows/forward-paper.yml").read_text()
    assert 'cron: "20 0 * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    assert "forward-paper-state" in workflow
    assert "scripts.forward_watchdog" in workflow
    assert "python -m trader --db runtime/trader.db backup" in workflow
    assert "activate-live" not in workflow.lower()
    assert "enable live trading" not in workflow.lower()
    for forbidden in ("ALPACA", "IBKR", "API_KEY", "secrets."):
        assert forbidden not in workflow


def test_minimal_forward_requirements_exclude_broker_sdks():
    requirements = Path("requirements-forward.txt").read_text().lower()
    for required in ("pydantic", "pandas", "numpy", "requests", "filelock"):
        assert required in requirements
    for forbidden in ("alpaca", "ib_async", "nautilus", "yfinance"):
        assert forbidden not in requirements
