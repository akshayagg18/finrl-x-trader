"""Extract real upstream bars, with provenance; never manufacture index prices."""

import hashlib, json, sqlite3
from pathlib import Path
import pandas as pd
from trader.data import SECTORS

c = sqlite3.connect("/tmp/finrl-source/finrl_trading.db")
for sym in SECTORS:
    df = pd.read_sql_query(
        "SELECT date,open,high,low,close,adj_close,volume FROM price_data WHERE ticker=? AND date BETWEEN ? AND ? ORDER BY date",
        c,
        params=(sym, "2020-12-01", "2025-10-07"),
    )
    if len(df) < 130:
        continue
    path = Path("sample_data") / (sym + ".csv")
    df.to_csv(path, index=False)
    path.with_suffix(".json").write_text(
        json.dumps(
            {
                "source": "Upstream data/finrl_trading.7z price_data table",
                "upstream_commit": "4409abe925c904e570be78ebfb5e77ac3491dff8",
                "symbol": sym,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "note": "Historical vendor snapshot; not certified point-in-time; raw OHLC used for fills, splits adjusted explicitly.",
            },
            indent=2,
        )
    )
