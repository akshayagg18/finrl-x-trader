# Broker connection guide

No credentials are needed for installation, historical backtesting, local simulation or dashboard use. No real orders were placed during development. Credentials below are supplied later, on your backend only. Do not paste them into dashboard fields, Git, screenshots or logs. Transfers and withdrawals are intentionally absent.

## Local simulation

Settings → Broker → local / simulation, then Save. Capital is $500 by default. Leave account blank for the default persistent ledger or choose a distinct local ledger name. This creates separate history, not an ownership transfer. Use a replay date covered by the bundled snapshot (2025-01-06 is tested). Current simulation uses cache freshness checks; choose Yahoo to fetch current completed daily bars.

## Alpaca (official alpaca-py SDK)

1. Create an Alpaca account with the appropriate trading permissions. Use a **dedicated** bot account without manual holdings or open orders. Fund it as appropriate. You may allocate $500 even if cash is larger; the rest is not allocated to the ledger.
2. Generate **paper** credentials first. Copy `.env.example` to `.env` and set only `ALPACA_PAPER_KEY` and `ALPACA_PAPER_SECRET`. Restart the backend to read them. Never reuse paper keys as live keys. The adapter constructs official SDK URLs from explicit mode; arbitrary broker endpoint URLs are not accepted.
3. In Settings → Broker choose alpaca / paper, enter the exact account UUID, check dedicated account, Save, then Test connection. To discover the UUID, the read-only connection test returns it; copy it to the account field and Save again. Test status is connectivity, not a claim of validated order execution.
4. Set Capital → allocated $500 (or your budget), Risk limits, Strategy and Data → yahoo. Download real bars. Check required-symbol coverage; stale/missing bars prevent execution. Quotes require current IEX data from Alpaca; subscription/permission restrictions may block quotes. This is reported, not substituted with simulated prices.
5. Clear the Portfolio replay date for current operation. Preview a dry cycle. Then Start automation. The NYSE scheduler reconciles orders/fills and uses DAY market orders, including eligible fractional quantities rounded down to six decimals. Small orders default to $1 minimum. Every asset is checked for tradable/active/fractional flags. Unsupported or restricted instruments fail closed. No margin borrowing, short selling, derivatives or leveraged funds are supported.
6. Observe actual paper fills, balances and order state through multiple sessions/restarts before enabling any real account. Paper/live external execution has **not** been verified in this installation without credentials.

For live, set separate `ALPACA_LIVE_KEY` / `ALPACA_LIVE_SECRET`, restart, choose alpaca / live with its correct account ID, test, and type **ENABLE LIVE TRADING** in the activation dialog. This one activation permits autonomous orders under saved limits; no per-order approval follows. Start automation explicitly. Switching broker/account, changing capital or strategy revokes activation. Risk limits are triggers, not guaranteed loss ceilings.

The local ledger applies broker-reported cumulative fill quantity/average price exactly once, including partials. Partial or accepted orders block new allocation until terminal/reconciled. A network timeout leaves the client ID persisted before submission. If the broker cannot resolve it, execution stops instead of resubmitting. Cancellation is followed by reconciliation before new allocation.

**Fee limitation:** Alpaca order objects do not report all regulatory/account activity fees. The adapter records fill prices and currently records zero per-order fees, which must not be interpreted as verified zero net fees. Full account-activity fee attribution remains unfinished. The ledger checks available cash and stops on a deficit; a dedicated account with extra unallocated cash can mask tiny fee discrepancies. Independently reconcile statements before relying on live net performance. Dividend/corporate-action attribution is also unfinished and unexpected position changes halt execution. These are software gaps, not credential-only verification tasks.

## Interactive Brokers (ib_async, TWS / IB Gateway)

The adapter is implemented for USD cash equities, SMART routing and **whole-share DAY market orders**. Fractional API eligibility is not assumed. Gateway must remain authenticated; the application does not collect your IBKR password or bypass session authentication.

1. Install current TWS or IB Gateway. Log into your paper account. Enable socket API access, configure trusted clients and the API port; disable API read-only only when ready for paper order tests.
2. Use a dedicated account. Set `IBKR_ACCOUNT` to the exact account ID. Paper accounts must start `DU`; live mode rejects `DU`. Typical Gateway ports are 4002 paper / 4001 live; TWS commonly uses 7497 / 7496. Set `IBKR_HOST`, `IBKR_PORT`, and a unique `IBKR_CLIENT_ID`.
3. Docker users: a Gateway on the host can be addressed as host.docker.internal; configure Gateway trusted IPs narrowly. Do not publish Gateway API sockets to the internet. The host port has to be reachable from the container.
4. Test connection in Settings. The adapter checks managed accounts and reads USD account summary, positions, contract qualifications and pending/completed orders. Quote access requires market-data entitlements; missing quotes halt execution.
5. The additional environment gate `IBKR_CONNECTED_VERIFIED=false` blocks all submission by default. Validate account/contract/order permissions with your paper Gateway and the session workflow. Then set it to true and restart for deliberate paper testing. This gate is separate from the one explicit live activation.
6. Set ibkr / paper, account ID and dedicated account; save capital/risk settings. Whole-share rounding may generate no orders in a $500 account, which is honestly displayed. IBKR commissions can be material for this budget; configure matching simulated costs when evaluating it.

Actual Gateway connectivity, exchange permissions, fee reporting, reconnect/session expiry, and broker-side orderRef recovery require external verification. The mock tests cover mode and fill normalization, not a working IBKR session. Orders absent from pending/completed APIs after a session reset remain ambiguous and block execution. This intentionally prefers a missed opportunity over a duplicate order. The adapter does not support portfolio transfers, fractional IBKR orders, options, futures, non-USD positions or cash sweeping.

## Ownership and recovery

Dedicated means there are no positions/orders outside this installation's ledger. A newly attached account with holdings is refused; it is never silently imported. Existing bot state is scoped by broker/mode/account and bound to broker identity. A mismatch, unexpected corporate action, external withdrawal, manual trade or unknown open order causes a halt. Extra account cash is not automatically allocated. External `include_deposits=true` is rejected until a verified cash-flow integration exists; adjust the explicit budget instead.

Before changing accounts, pause/stop, cancel and reconcile known open orders. Switching accounts does not liquidate or move the old account, and does not allow one scheduler to operate multiple accounts. An existing filled portfolio can remain on a previous broker after switching; you remain responsible for monitoring it. Use a separate controlled instance only after carefully isolating account ownership.

For an uncertain submission, inspect the durable order ID and broker records. Do not delete the order row, edit quantities, or reset the database to force a retry. Reconcile the account before acknowledging an interrupted cycle. Automated repair of an unresolvable submission is intentionally absent. Keep backups and consult logs; emergency liquidation cannot guarantee liquidity or fill success.

## Intraday extension status

No crypto credentials are required or consumed. OKX access currently uses public history and instrument metadata only. No private crypto adapter is operational; do not supply keys expecting live execution. Singapore eligibility, regional endpoint, pairs, tariff and trade-only permissions require verification before that integration is completed. Existing Alpaca/IBKR credentials do not activate intraday research strategies. This is an implementation limitation in addition to unavailable credentials.
