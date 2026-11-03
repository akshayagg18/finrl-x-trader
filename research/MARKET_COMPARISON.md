# Intraday market comparison — 2026-11-03 UTC

Status: preliminary research with explicit unresolved account eligibility. No exchange is represented as operational for Singapore live trading.

| Market | $500 practicality | Costs and execution | Data available here | Unresolved gate |
|---|---|---|---|---|
| BTC/ETH spot | Fractional orders; no equity settlement delay; 24/7 | Model 10 bps taker fee plus 5 bps adverse execution per side, **assumptions**, not verified Singapore tariff | Global OKX 15-minute candles, Nov 2024–Oct 2026; live instrument metadata includes tickSz, lotSz, minSz | Singapore entity onboarding, available pairs, regional API host, fee tier and trading permission |
| U.S. equities | Cash account needs settled funds; whole-share constraints can prevent trades | IBKR published U.S. tiered minimum $0.35/order; fixed minimum $1/order, subject to caps and pass-through charges. Our initial equity model of 1 bp fees is **not** an IBKR tariff model | Yahoo 15-minute bars, roughly 60 trading days; no historical NBBO | Broker residency eligibility, fraction/order-type support, data entitlement, account restrictions |
| Major forex | USD conversion is useful, speculative intraday deployment not selected | Spreads, minimum commissions and currency conversion can dominate $500 | Not acquired | No leveraged FX or derivatives implementation |

## Current U.S. rules

[FINRA Regulatory Notice 26-10](https://www.finra.org/rules-guidance/notices/26-10), retrieved 2026-11-03, states that amendments replacing the pattern-day-trader count and $25,000 minimum became effective June 4, 2026, with a phase-in ending October 20, 2027. **The effective date does not establish that an individual broker has transitioned.** Broker-specific applicability remains unverified.

[FINRA current investor guidance](https://www.finra.org/investors/investing/investment-products/stocks/day-trading), retrieved 2026-11-03: most equity settlement is T+1; cash-account good-faith/free-riding restrictions still apply; borrowing requires minimum margin equity. The research implementation forbids leverage and conservatively prevents new equity purchases for the rest of a session after a sale. This is not yet a complete settled-funds broker ledger.

## Sources and limits

- [OKX Singapore fee page](https://www.okx.com/en-sg/fees), HTTP 200, retrieved 2026-11-03. Region-dependent rendered page did not establish a reliable numeric Singapore tariff. Do not infer local fees or legal eligibility from global market-data access.
- [OKX API documentation](https://www.okx.com/docs-v5/en/), HTTP 200. Public historical candles and instrument endpoints were exercised. Private trading has **not** been exercised. No withdrawal API is implemented.
- [Alpaca international accounts](https://docs.alpaca.markets/docs/international-accounts), HTTP 200. This retrieval alone does not verify Singapore retail account approval or current account restrictions. Existing Alpaca integration remains separately available, pending credentials.
- [IBKR U.S. commissions](https://www.interactivebrokers.com/en/pricing/commissions-stocks.php), HTTP 200. Site distinguishes tiered/fixed and IBKR Lite eligibility (U.S. residents); Singapore GST can apply. Do not assume commission-free IBKR Lite for Singapore.
- Yahoo chart endpoint metadata and SHA-256 are stored beside each data file. Intraday archive access is limited; two-year equity evaluation has not been achieved.

Crypto has better freely accessible history and fractional sizing for this experiment, but higher assumed turnover costs, stablecoin risk and unresolved regional access. Equities have better-known exchange-session structure but limited free intraday history and material cash/quantity restrictions. Neither is established as more profitable. Historical spreads and depth are unavailable in the candle snapshots. Service eligibility must be confirmed against the actual Singapore account before enabling execution.
