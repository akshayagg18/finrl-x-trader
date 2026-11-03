# Intraday implementation continuation

- Add leakage-controlled random forest and gradient-boosted regressors, versioned artifacts and locked chronological evaluation.
- Add 5-minute data and evaluate ML against cash/hold/simple baselines with costs and walk-forward folds. Previously inspected October periods are not described as fully unseen.
- Share portfolio loss constraints between swing and intraday; implement explicit T+1 settled-funds tracking in the execution strategy.
- Extend Nautilus replay to continuous positions without terminal liquidation; persist immutable sessions and deterministic execution identities, resume after restart through replay reconstruction.
- Integrate replay scheduling into the existing scheduler, scoped virtual allocations, pause/kill protection, durable records and dashboard controls.
- Add ML and replay tests plus existing regression/UI tests. Keep unavailable external venue routing explicitly disabled.

Implemented and verified: supervised models/artifacts, 5m/15m walk-forward study, daily/peak/capital loss gate shared with swing strategies, T+1 proceeds ledger, continuous deterministic local replay, atomic restart/deduplication, central scheduler integration, dashboard model/replay controls, metrics and CCXT transport contracts. Full test suite: 56 passed.

Still open: wire external account routing/reconciliation with ownership isolation; regional OKX verification; fractional equity instrument handling and live-feed paper simulation. Historical local replay and broker paper execution are deliberately distinct. No strategy qualified for live use.
