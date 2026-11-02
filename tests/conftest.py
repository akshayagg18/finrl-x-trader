import pytest
from trader.service import Service


@pytest.fixture
def service(tmp_path):
    return Service(tmp_path / "trader.db")


@pytest.fixture
def small_settings(service):
    s = service.db.settings()
    s.strategy.name = "equal_weight"
    s.strategy.universe = ["AAPL", "MSFT"]
    return s
