# Intraday strategy research — implementation status

Implemented baseline hypotheses: lagged lookback momentum; lagged deviation below a rolling mean; cash; buy-and-hold. These are simple reproducible research baselines, not established profitable strategies. Signal features only use completed prior bars; market orders execute against modeled bid/ask at the next bar open. Stops operate at bar boundaries and can gap.

The preliminary search uses lookbacks 16/32/64 on 15-minute bars, a fixed 0.3% threshold, 80% maximum deployment, 3% stop and 15% drawdown halt. The protocol is written before test evaluation. Crypto has chronological training and validation over different years. Equity training/validation is necessarily short due to free-data coverage. October 2026 is held apart for final comparison. Cost sensitivity uses 1.5× and 2× fees/adverse execution.

Not implemented yet: ML/FreqAI training, walk-forward model versions, 5-minute comparisons, regime classification, validated ensembles, and RL adaptation. Reinforcement learning is not justified by current data/verification and is deliberately not deployed. ML must later be compared with the same simple baselines using label-maturity purging and an untouched holdout.

No academic edge is claimed for these baseline rules. Candle execution assumptions, short equity coverage and estimated tariffs are qualification blockers, independently of any positive result.
