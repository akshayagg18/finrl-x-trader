"""Locked validation selection and walk-forward refits; no profitability guarantee."""

import gzip
from pathlib import Path

from trader.db import dumps
from trader.intraday.engine import backtest
from trader.intraday.ml import train

OUT = Path("research/intraday_ml")
OUT.mkdir(exist_ok=True)
PROTOCOL = {
    "validation": ["2025-07-01", "2025-08-31"],
    "initial_cutoff": "2025-07-01",
    "walk_forward": [
        ["2026-01-01", "2026-02-28"],
        ["2026-07-01", "2026-08-31"],
        ["2026-10-01", "2026-10-31"],
    ],
    "families": ["boosted", "forest"],
    "horizons": [8, 16],
    "buffers": [0.001, 0.003],
    "selection": "Highest validation net return among models with drawdown better than -15%; no test-based reselection. Cash is deployment default if evidence fails.",
    "costs": {"fee_bps": 10, "friction_bps": 5},
    "limitations": [
        "October baseline returns previously inspected; not a pristine research holdout",
        "Fixed data snapshot, modeled execution quotes, USDT/USD parity",
        "No new market data after model selection; historical walk-forward, not prospective proof",
    ],
}
(OUT / "protocol.json").write_text(dumps(PROTOCOL))
rows = []
for interval in [15, 5]:
    for symbol in ["BTC-USDT", "ETH-USDT"]:
        if not Path(f"research/intraday/data/{symbol}_{interval}m.csv").exists():
            continue
        candidates = []
        for family in PROTOCOL["families"]:
            for horizon in PROTOCOL["horizons"]:
                model = train(
                    symbol, interval, PROTOCOL["initial_cutoff"], family, horizon
                )
                for buffer in PROTOCOL["buffers"]:
                    c = {
                        "symbol": symbol,
                        "interval": interval,
                        "strategy": "ml",
                        "model_id": model["id"],
                        "ml_buffer": buffer,
                    }
                    r = backtest(c, *PROTOCOL["validation"])
                    candidates.append(
                        {
                            "family": family,
                            "horizon": horizon,
                            "config": c,
                            "return": r["net_return"],
                            "drawdown": r["max_drawdown"],
                            "fills": len(r["fills"]),
                        }
                    )
        eligible = [r for r in candidates if r["drawdown"] > -0.15]
        if not eligible:
            raise RuntimeError("No risk-eligible candidate")
        selected = max(eligible, key=lambda r: r["return"])
        (OUT / f"{symbol}_{interval}_locked.json").write_text(
            dumps(
                {
                    "candidates": candidates,
                    "selected": selected,
                    "locked_before_walk_forward": True,
                }
            )
        )
        print("LOCKED", symbol, interval, selected, flush=True)
        for start, end in PROTOCOL["walk_forward"]:
            model = train(
                symbol, interval, start, selected["family"], selected["horizon"]
            )
            c = {**selected["config"], "model_id": model["id"]}
            cases = [
                ("ml", c),
                ("cash", {**c, "strategy": "cash"}),
                ("hold", {**c, "strategy": "hold"}),
                ("momentum", {**c, "strategy": "momentum"}),
                ("gross", {**c, "fee_bps": 0, "friction_bps": 0}),
                ("cost_1.5x", {**c, "fee_bps": 15, "friction_bps": 7.5}),
                ("cost_2x", {**c, "fee_bps": 20, "friction_bps": 10}),
            ]
            for label, config in cases:
                r = backtest(config, start, end)
                # Keep actual test fills and equity but avoid copying redundant development paths.
                name = f"{symbol}_{interval}_{start}_{label}"
                with gzip.open(OUT / (name + ".json.gz"), "wt") as f:
                    f.write(dumps(r))
                (OUT / (name + ".json")).unlink(missing_ok=True)
                brief = {
                    "symbol": symbol,
                    "interval": interval,
                    "start": start,
                    "end": end,
                    "case": label,
                    "return": r["net_return"],
                    "drawdown": r["max_drawdown"],
                    "ending_equity": r["ending_equity"],
                    "fills": len(r["fills"]),
                    "model_id": model["id"],
                }
                rows.append(brief)
                print(dumps(brief), flush=True)
        (OUT / "summary.json").write_text(dumps(rows))
print("COMPLETE", flush=True)
