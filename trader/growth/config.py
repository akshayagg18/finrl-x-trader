from pydantic import BaseModel, ConfigDict, Field


class GrowthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    capital: float = Field(500, gt=0, le=100000)
    deployment: float = Field(0.6, gt=0, le=0.6)
    per_asset: float = Field(0.3, gt=0, le=0.3)
    reserve: float = Field(0.4, ge=0.4, lt=1)
    trade_risk: float = Field(0.005, gt=0, le=0.005)
    daily_loss: float = Field(0.02, gt=0, le=0.02)
    drawdown_halt: float = Field(0.08, gt=0, le=0.08)
    fee_bps: float = Field(10, ge=0, le=100)
    friction_bps: float = Field(5, ge=0, le=100)
    fees_verified: bool = False
    min_validation_exits: int = Field(20, ge=20)
    seed: int = 17
