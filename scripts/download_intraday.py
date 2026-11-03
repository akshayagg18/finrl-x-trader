"""Fetch genuine closed OKX spot candles and Yahoo equity bars, recording provenance."""

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path("research/intraday/data")


def save(name, frame, source, metadata=None):
    frame = frame.sort_index()
    if frame.index.has_duplicates or frame.empty:
        raise ValueError("Empty or duplicated data")
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / (name + ".csv")
    frame.to_csv(path, index_label="timestamp")
    info = {
        "source": source,
        "acquired": datetime.now(UTC).isoformat(),
        "first": str(frame.index[0]),
        "last": str(frame.index[-1]),
        "bars": len(frame),
        "convention": "UTC bar opening timestamps; completed bars only",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "metadata": metadata,
    }
    path.with_suffix(".json").write_text(json.dumps(info, indent=2))
    return info


def crypto(symbol, start="2024-11-01", end="2026-11-01", interval=15):
    url = "https://www.okx.com/api/v5/market/history-candles"
    lo = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    hi = int(pd.Timestamp(end, tz="UTC").timestamp() * 1000)
    cursor = hi
    rows = []
    while cursor > lo:
        r = requests.get(
            url,
            params={
                "instId": symbol,
                "bar": f"{interval}m",
                "after": cursor,
                "limit": 300,
            },
            timeout=30,
        )
        r.raise_for_status()
        payload = r.json()
        if payload.get("code") != "0":
            raise ValueError(payload)
        batch = payload["data"]
        if not batch:
            break
        oldest = min(int(x[0]) for x in batch)
        if oldest >= cursor:
            raise ValueError("Pagination failed to advance")
        rows.extend(x for x in batch if lo <= int(x[0]) < hi and x[-1] == "1")
        cursor = oldest
        time.sleep(0.12)
    frame = pd.DataFrame(
        rows,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "base_volume",
            "quote_volume",
            "confirmed",
        ],
    )
    frame.index = pd.to_datetime(
        frame.pop("timestamp").astype("int64"), unit="ms", utc=True
    )
    frame = frame[["open", "high", "low", "close", "volume"]].astype(float)
    instrument = requests.get(
        "https://www.okx.com/api/v5/public/instruments",
        params={"instType": "SPOT", "instId": symbol},
        timeout=30,
    ).json()
    return save(
        symbol + f"_{interval}m",
        frame,
        url,
        {
            "instrument": instrument,
            "requested_start": start,
            "requested_end": end,
            "venue": "Global OKX data; Singapore account instrument access unverified",
        },
    )


def equity(symbol, interval=15):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
    r = requests.get(
        url,
        params={"range": "60d", "interval": f"{interval}m", "includePrePost": "false"},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    r.raise_for_status()
    obj = r.json()["chart"]["result"][0]
    frame = pd.DataFrame(
        obj["indicators"]["quote"][0],
        index=pd.to_datetime(obj["timestamp"], unit="s", utc=True),
    )
    frame = frame.dropna()
    frame = frame[
        frame.index + pd.Timedelta(minutes=interval) < pd.Timestamp.now(tz="UTC")
    ]
    return save(
        symbol + f"_{interval}m",
        frame,
        url,
        {
            "adjustment": "vendor intraday OHLC; corporate-action vintage not certified",
            "coverage_limit": "60 days; insufficient for long-term qualification",
        },
    )


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor

    def run(symbol):
        try:
            info = crypto(symbol) if "-" in symbol else equity(symbol)
            print(symbol, info, flush=True)
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            print(symbol, type(exc).__name__, str(exc), flush=True)

    with ThreadPoolExecutor(4) as pool:
        list(pool.map(run, ["BTC-USDT", "ETH-USDT", "AAPL", "SPY", "QQQ"]))
