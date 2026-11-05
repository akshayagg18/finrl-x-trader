# Selected 20% candidate: prospective forward paper

The frozen `trend_100_momentum_90_weekly_btc_gate` candidate now has an
isolated, persistent forward-paper account. It starts with $500, permits at most
20% per asset and 40% total deployment, volatility-scales toward 30% annualized,
and rebalances no more than once per UTC week. It is long-only and otherwise
holds cash.

The first genuine public observation was recorded on **6 November 2026 at
03:20 Singapore time** (5 November 19:20 UTC) from Binance spot. Prior completed
daily data produced target weights of 19.06% BTC and 13.82% ETH. The simulated
account bought 0.00125101 BTC and 0.03064032 ETH, retained $335.37 cash, and
ended the initial mark at $499.75 after modeled spread, 5 bp adverse execution,
and 10 bp fees. The initial -0.049% result is transaction cost, not evidence of
strategy failure or success.

This is one observation and one catch-up decision after activation. It is not a
weekly record. The system requires at least 12 newly elapsed decision weeks plus
profitability, doubled-cost, drawdown, activity and uncertainty checks. Even if
those gates pass, automatic broker promotion remains disabled.

## Operation

The application scheduler checks once per day, obtains completed Binance daily
history and current bid/ask quotes, stores an immutable observation, and
reconstructs the virtual account deterministically. Stable fill identifiers
prevent duplicate virtual orders after restart. Configuration freezes after the
first observation. Global kill stops collection. Network, stale-data, malformed
history and calculation failures stop the account and write an audit event.

Start or inspect from Research & backtests → Selected 20% candidate, or run:

```sh
python -m scripts.start_defensive_forward --db runtime/trader.db --capital 500
python -m trader serve
```

The process must remain running to collect subsequent observations. The SQLite
database is private runtime state and is excluded from Git; use the documented
backup workflow. `initial_observation.json` contains only the public-data
verification snapshot.

No broker credentials were used. No broker-paper or real order was submitted.
Live orders are impossible from this subsystem.
