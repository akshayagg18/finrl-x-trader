"""Download and freeze Binance public hourly spot archives for regime research.

The archive is used only as a long-history research source. It does not imply
Binance account availability and is never substituted for OKX execution data.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

OUT = Path("research/strategy_v2/data")
BASE = "https://data.binance.vision/data/spot/monthly/klines"
SYMBOLS = ("BTCUSDT", "ETHUSDT")
START = pd.Period("2017-08", "M")
END = pd.Period("2026-10", "M")
COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "trades",
    "taker_base",
    "taker_quote",
    "ignore",
]


def _fetch(symbol: str, period: pd.Period) -> tuple[pd.DataFrame, dict]:
    name = f"{symbol}-1h-{period}.zip"
    url = f"{BASE}/{symbol}/1h/{name}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    archive_hash = hashlib.sha256(response.content).hexdigest()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        members = archive.namelist()
        if len(members) != 1:
            raise ValueError(f"Unexpected archive members for {name}")
        raw = archive.read(members[0])
    frame = pd.read_csv(io.BytesIO(raw), header=None, names=COLUMNS)
    # Binance changed public archive timestamps from milliseconds to microseconds.
    unit = "us" if int(frame.open_time.iloc[0]) > 10**14 else "ms"
    frame.index = pd.to_datetime(frame.pop("open_time"), unit=unit, utc=True)
    frame.index.name = "timestamp"
    frame = frame[["open", "high", "low", "close", "volume"]].astype(float)
    return frame, {
        "url": url,
        "http_last_modified": response.headers.get("last-modified"),
        "archive_sha256": archive_hash,
        "bars": len(frame),
    }


def download(symbol: str) -> dict:
    periods = list(pd.period_range(START, END, freq="M"))
    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, dict] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_fetch, symbol, period): period for period in periods}
        for future in as_completed(futures):
            period = str(futures[future])
            try:
                frame, source = future.result()
                frames[period] = frame
                sources[period] = source
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    errors[period] = "archive unavailable"
                else:
                    raise
    if not frames:
        raise ValueError(f"No public archive data for {symbol}")
    data = pd.concat([frames[key] for key in sorted(frames)]).sort_index()
    data = data[~data.index.duplicated(keep="last")]
    if not data.index.is_monotonic_increasing:
        raise ValueError("Non-monotonic archive timestamps")
    if not data[["open", "high", "low", "close", "volume"]].notna().all().all():
        raise ValueError("Missing OHLCV values")
    if (data[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("Nonpositive prices")
    if (data.high < data[["open", "close", "low"]].max(axis=1)).any() or (
        data.low > data[["open", "close", "high"]].min(axis=1)
    ).any():
        raise ValueError("Invalid OHLC bounds")
    irregular = data.index[
        (data.index.minute != 0)
        | (data.index.second != 0)
        | (data.index.microsecond != 0)
    ]
    expected = pd.date_range(data.index[0], data.index[-1], freq="1h", tz="UTC")
    missing = expected.difference(data.index)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{symbol}_1h.csv.gz"
    data.to_csv(path, compression={"method": "gzip", "compresslevel": 9, "mtime": 0})
    manifest = {
        "provider": "Binance public data archive",
        "market": f"{symbol[:-4]}/USDT spot",
        "purpose": "cross-venue long-history research only; not OKX execution evidence",
        "interval": "1h UTC opening timestamps",
        "requested_months": [str(START), str(END)],
        "first": data.index[0].isoformat(),
        "last": data.index[-1].isoformat(),
        "bars": len(data),
        "missing_hours": len(missing),
        "missing_examples": [x.isoformat() for x in missing[:100]],
        "irregular_partial_bars": len(irregular),
        "irregular_examples": [x.isoformat() for x in irregular[:100]],
        "unavailable_months": errors,
        "acquired_at": datetime.now(UTC).isoformat(),
        "csv_gzip_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "monthly_sources": sources,
        "limitations": [
            "Current vendor archives can contain revisions and are not vintage snapshots.",
            "Binance history cannot establish OKX Singapore fees, fills, or eligibility.",
            "USDT is treated as USD parity in portfolio reporting.",
        ],
    }
    path.with_suffix("").with_suffix(".json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return manifest


def main() -> None:
    for symbol in SYMBOLS:
        manifest = download(symbol)
        print(
            json.dumps(
                {
                    "symbol": symbol,
                    "bars": manifest["bars"],
                    "first": manifest["first"],
                    "last": manifest["last"],
                    "missing_hours": manifest["missing_hours"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
