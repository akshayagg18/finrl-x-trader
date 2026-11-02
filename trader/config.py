from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BrokerSettings(Strict):
    broker: Literal["local", "alpaca", "ibkr"] = "local"
    mode: Literal["simulation", "paper", "live"] = "simulation"
    account: str = ""
    dedicated_account: bool = False

    @model_validator(mode="after")
    def valid(self):
        if (self.broker == "local") != (self.mode == "simulation"):
            raise ValueError(
                "Local requires simulation; external brokers require paper or live"
            )
        return self


class Capital(Strict):
    allocated: float = Field(500, gt=0, le=1e7)
    method: Literal["fixed", "equity_percent"] = "fixed"
    equity_percent: float = Field(0.25, gt=0, le=1)
    deployment: float = Field(0.8, ge=0, le=1)
    cash_reserve: float = Field(0.2, ge=0, le=1)
    reinvest_profits: bool = True
    include_deposits: bool = False
    fractional: bool = True
    min_order: float = Field(1, ge=1, le=100000)


class Risk(Strict):
    max_position: float = Field(0.25, gt=0, le=1)
    max_sector: float = Field(0.5, gt=0, le=1)
    max_holdings: int = Field(5, ge=1, le=50)
    max_order: float = Field(100, gt=0, le=1e6)
    max_turnover: float = Field(0.5, gt=0, le=2)
    max_daily_loss: float = Field(0.03, gt=0, le=1)
    max_drawdown: float = Field(0.15, gt=0, le=1)
    max_capital_loss: float = Field(0.2, gt=0, le=1)
    stop_loss: float = Field(0.08, gt=0, le=1)
    trailing_stop: float | None = Field(0.12, gt=0, le=1)
    max_orders_day: int = Field(15, ge=1, le=1000)
    max_volatility: float = Field(0.85, gt=0, le=10)
    volatility_target: float = Field(0.3, gt=0, le=5)
    failure_limit: int = Field(3, ge=1, le=100)
    loss_action: Literal["halt", "liquidate"] = "halt"


class Strategy(Strict):
    name: Literal["adaptive_rotation", "equal_weight", "rolling_ml"] = (
        "adaptive_rotation"
    )
    universe: list[str] = Field(
        default_factory=lambda: [
            "AAPL",
            "MSFT",
            "NVDA",
            "AMZN",
            "JPM",
            "GS",
            "XOM",
            "CVX",
            "JNJ",
            "PG",
            "KO",
            "NEE",
        ]
    )
    rebalance: Literal["daily", "weekly", "monthly"] = "weekly"
    model_version: int | None = None
    rotation_version: Literal["v1.2.1", "v1.2.2"] = "v1.2.2"
    top_n_per_group: int = Field(2, ge=1, le=10)

    @model_validator(mode="after")
    def valid(self):
        import re

        if (
            not self.universe
            or len(self.universe) > 50
            or len(set(self.universe)) != len(self.universe)
        ):
            raise ValueError("Universe requires 1–50 unique symbols")
        if any(not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", s) for s in self.universe):
            raise ValueError("Invalid US symbol")
        return self


class Data(Strict):
    provider: Literal["cache", "yahoo"] = "cache"
    max_age_hours: float = Field(96, ge=1, le=168)
    timeout_seconds: int = Field(15, ge=1, le=60)


class Simulation(Strict):
    slippage_bps: float = Field(5, ge=0, le=500)
    spread_bps: float = Field(4, ge=0, le=500)
    commission_fixed: float = Field(0, ge=0, le=100)
    commission_bps: float = Field(0, ge=0, le=100)
    fill_fraction: float = Field(1, gt=0, le=1)


class Automation(Strict):
    monitor_seconds: int = Field(60, ge=10, le=3600)
    execution_minutes_after_open: int = Field(15, ge=1, le=120)


class Settings(Strict):
    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    capital: Capital = Field(default_factory=Capital)
    risk: Risk = Field(default_factory=Risk)
    strategy: Strategy = Field(default_factory=Strategy)
    data: Data = Field(default_factory=Data)
    simulation: Simulation = Field(default_factory=Simulation)
    automation: Automation = Field(default_factory=Automation)


PRESETS = {
    "Conservative": Risk(
        max_position=0.2,
        max_sector=0.35,
        max_order=75,
        max_turnover=0.3,
        max_daily_loss=0.02,
        max_drawdown=0.1,
        stop_loss=0.06,
    ).model_dump(),
    "Balanced": Risk().model_dump(),
    "Aggressive": Risk(
        max_position=0.35,
        max_sector=0.6,
        max_order=150,
        max_turnover=0.8,
        max_daily_loss=0.05,
        max_drawdown=0.25,
        stop_loss=0.12,
    ).model_dump(),
}
