"""Real OHLCV only; provenance retained, no synthetic fallback."""

from pathlib import Path
import hashlib
import json
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["SPY", "QQQ", "^GSPC", "^VIX"]
SECTORS = {
    "AAPL": "Technology",
    "MSFT": "Technology",
    "NVDA": "Technology",
    "AMZN": "Consumer Discretionary",
    "META": "Communication",
    "GOOGL": "Communication",
    "TSLA": "Consumer Discretionary",
    "JPM": "Financials",
    "GS": "Financials",
    "HD": "Consumer Discretionary",
    "CAT": "Industrials",
    "UNP": "Industrials",
    "DE": "Industrials",
    "AXP": "Financials",
    "XOM": "Energy",
    "CVX": "Energy",
    "COP": "Energy",
    "FCX": "Materials",
    "BHP": "Materials",
    "GLD": "Commodity",
    "SLV": "Commodity",
    "JNJ": "Healthcare",
    "PG": "Consumer Staples",
    "KO": "Consumer Staples",
    "UNH": "Healthcare",
    "NEE": "Utilities",
    "DUK": "Utilities",
    "PEP": "Consumer Staples",
    "SPY": "Broad Market",
    "QQQ": "Broad Market",
}
ALLOWED = set(SECTORS)


class DataError(ValueError):
    pass


class MarketData:
    def __init__(self, cache):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)

    def path(self, symbol):
        import re

        if not re.fullmatch(r"\^?[A-Z][A-Z0-9.\-]{0,9}", symbol):
            raise DataError("Invalid symbol")
        return self.cache / (symbol.replace("^", "INDEX_") + ".csv")

    def load(self, symbols, through=None):
        result = {}
        for s in sorted(set(symbols)):
            path = self.path(s)
            bundled = ROOT / "sample_data" / path.name
            if not path.exists() and bundled.exists():
                path = bundled
            if not path.exists():
                raise DataError(
                    f"No real data cached for {s}; refresh or import OHLCV CSV"
                )
            df = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
            if through is not None:
                df = df.loc[: pd.Timestamp(through)]
            validate(df, s)
            # Consistent split/dividend adjusted research units, never sent as live prices.
            if "adj_close" in df and df.adj_close.notna().all():
                factor = df.adj_close / df.close
                for col in ["open", "high", "low", "close"]:
                    df[col] = df[col] * factor
            result[s] = df
        return result

    def refresh(self, symbols, timeout=15):
        start = int(pd.Timestamp("2017-01-01", tz="UTC").timestamp())
        end = int(datetime.now(timezone.utc).timestamp())
        outcomes = {}
        for symbol in sorted(set(symbols)):
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            try:
                r = requests.get(
                    url,
                    params={"period1": start, "period2": end, "interval": "1d"},
                    headers={"User-Agent": "Mozilla/5.0 FinRL local research"},
                    timeout=timeout,
                )
                r.raise_for_status()
                item = r.json()["chart"]["result"][0]
                df = pd.DataFrame(
                    item["indicators"]["quote"][0],
                    index=pd.to_datetime(item["timestamp"], unit="s", utc=True)
                    .tz_convert("America/New_York")
                    .tz_localize(None)
                    .normalize(),
                )
                df.index.name = "date"
                df["adj_close"] = (
                    item["indicators"]
                    .get("adjclose", [{}])[0]
                    .get("adjclose", df["close"])
                )
                # Only completed daily bars; never silently use intraday close.
                today = (
                    pd.Timestamp.now(tz="America/New_York")
                    .tz_localize(None)
                    .normalize()
                )
                df = df[df.index < today].dropna(
                    subset=["open", "close", "high", "low"]
                )

                validate(df, symbol)
                dest = self.path(symbol)
                temp = dest.with_suffix(".tmp")
                df.to_csv(temp)
                temp.replace(dest)
                meta = {
                    "source": url,
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
                    "adjustment": "raw OHLCV, Yahoo historical revisions possible",
                }
                dest.with_suffix(".json").write_text(json.dumps(meta, indent=2))
                outcomes[symbol] = {"bars": len(df), "last": str(df.index[-1].date())}
            except Exception as exc:
                outcomes[symbol] = {"error": type(exc).__name__}
        return outcomes

    def inventory(self):
        paths = {p.name: p for p in (ROOT / "sample_data").glob("*.csv")}
        paths.update({p.name: p for p in self.cache.glob("*.csv")})
        result = []
        for p in paths.values():
            df = pd.read_csv(p)
            result.append(
                {
                    "symbol": p.stem.replace("INDEX_", "^"),
                    "bars": len(df),
                    "first": df.date.iloc[0],
                    "last": df.date.iloc[-1],
                    "bundled": p.parent.name == "sample_data",
                }
            )
        return result


def validate(df, symbol="data"):
    if len(df) < 2 or not {"open", "high", "low", "close", "volume"} <= set(df.columns):
        raise DataError(f"{symbol}: missing OHLCV or insufficient history")
    values = df[["open", "high", "low", "close"]].to_numpy(float)
    if (
        not np.isfinite(values).all()
        or (values <= 0).any()
        or df.index.duplicated().any()
    ):
        raise DataError(f"{symbol}: invalid, duplicate or missing prices")
    if (df.high < df.low).any() or (df.volume < 0).any():
        raise DataError(f"{symbol}: invalid range/volume")


def aligned(data):
    dates = None
    for df in data.values():
        dates = df.index if dates is None else dates.intersection(df.index)
    if dates is None or len(dates) < 130:
        raise DataError("Require at least 130 common trading sessions")
    # No forward fill across missing sessions.
    latest = min(df.index[-1] for df in data.values())
    if any(df.index[-1] != latest for df in data.values()):
        raise DataError("Latest bar dates disagree across instruments")
    return dates.sort_values()
