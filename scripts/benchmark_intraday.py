"""Predeclared chronological evaluation, isolated from deployed settings."""

import json
from pathlib import Path

from trader.db import dumps
from trader.intraday.engine import backtest

OUT = Path("research/intraday/results")
OUT.mkdir(parents=True, exist_ok=True)
PROTOCOL = {
    "crypto_train": ["2024-11-01", "2025-10-31"],
    "crypto_validation": ["2025-11-01", "2026-07-31"],
    "equity_train": ["2026-08-10", "2026-09-04"],
    "equity_validation": ["2026-09-08", "2026-09-30"],
    "common_test": ["2026-10-01", "2026-10-30"],
    "selection": "Highest validation net return among candidates whose training return is positive and drawdown <15%; otherwise no qualified candidate, evaluate best validation candidate for diagnostic purposes only",
    "costs": "Crypto 10bps fee +5bps execution per side; equity 1bp fee +2bps execution per side, estimates not verified account tariffs",
    "live_qualification": "No live qualification from short equity history, assumed quotes, or unverified venue access",
}
(OUT / "protocol.json").write_text(dumps(PROTOCOL))
rows = []
for symbol in ["BTC-USDT", "ETH-USDT", "AAPL", "SPY", "QQQ"]:
    market = "crypto" if "-" in symbol else "equity"
    base = {
        "symbol": symbol,
        "allocation": 0.8,
        "fee_bps": 10 if market == "crypto" else 1,
        "friction_bps": 5 if market == "crypto" else 2,
    }
    candidates = []
    for strategy in ["momentum", "reversion"]:
        for lookback in [16, 32, 64]:
            c = {**base, "strategy": strategy, "lookback": lookback}
            results = []
            for phase in ["train", "validation"]:
                name = f"{symbol}_{strategy}_{lookback}_{phase}"
                path = OUT / (name + ".json")
                r = (
                    json.loads(path.read_text())
                    if path.exists()
                    else backtest(c, *PROTOCOL[market + "_" + phase])
                )
                path.write_text(dumps(r))
                results.append(r)
                print(name, r["net_return"], len(r["fills"]), flush=True)
            candidates.append((c, *results))
    eligible = [
        x for x in candidates if x[1]["net_return"] > 0 and x[1]["max_drawdown"] > -0.15
    ]
    selected = max(eligible or candidates, key=lambda x: x[2]["net_return"])
    c = selected[0]
    (OUT / f"{symbol}_locked.json").write_text(
        dumps(
            {"selected": c, "training_eligible": bool(eligible), "test_not_used": True}
        )
    )
    cases = [
        ("selected", c),
        ("cash", {**base, "strategy": "cash"}),
        ("hold", {**base, "strategy": "hold"}),
        ("gross", {**c, "fee_bps": 0, "friction_bps": 0}),
        (
            "cost_1.5x",
            {
                **c,
                "fee_bps": c["fee_bps"] * 1.5,
                "friction_bps": c["friction_bps"] * 1.5,
            },
        ),
        (
            "cost_2x",
            {**c, "fee_bps": c["fee_bps"] * 2, "friction_bps": c["friction_bps"] * 2},
        ),
    ]
    for label, config in cases:
        r = backtest(config, *PROTOCOL["common_test"])
        (OUT / f"{symbol}_{label}_test.json").write_text(dumps(r))
        brief = {
            "symbol": symbol,
            "case": label,
            "net_return": r["net_return"],
            "ending_equity": r["ending_equity"],
            "max_drawdown": r["max_drawdown"],
            "fills": len(r["fills"]),
            "config": config,
        }
        rows.append(brief)
        print(dumps(brief), flush=True)
(OUT / "summary.json").write_text(dumps(rows))
