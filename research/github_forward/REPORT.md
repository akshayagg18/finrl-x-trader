# Free GitHub-hosted forward-paper verification

The public repository's daily workflow is active. It requires no laptop, VPS,
broker credential or paid data service.

Two initial integration runs on 7 November 2026 reached the paper operation but
failed before persistence because the snapshot command imported dependencies
outside the intentionally minimal environment. No state branch or observation
claim was retained from those failed runs. The workflow was corrected to use
the database backup API directly.

Run `42358045092` then completed every step and created
`forward-paper-state` at commit `3f2874d`. The first authoritative status was:

- active: true
- observations: 1
- decision weeks: 1
- ending virtual equity: $500.00
- error: null
- live orders possible: false

The strategy's BTC gate was closed, so it correctly remained in cash. This is a
real public-data observation and an honest no-trade decision.

Run `42358101487` executed again on the same UTC day, restored the state branch,
completed successfully and left the observation/decision counts at one. No new
state commit was necessary. This verifies daily idempotency and duplicate
prevention across separate ephemeral GitHub runners.

The cron schedule is 00:20 UTC, approximately 08:20 Singapore time. GitHub can
delay or miss scheduled jobs; failures remain visible in Actions and the
qualification period extends rather than backfilling false observations.

State: <https://github.com/akshayagg18/finrl-x-trader/blob/forward-paper-state/status.json>

Successful run: <https://github.com/akshayagg18/finrl-x-trader/actions/runs/42358045092>

Idempotency run: <https://github.com/akshayagg18/finrl-x-trader/actions/runs/42358101487>

Full repository regression: **113 passed**, 5,078 dependency deprecation
warnings in 61.38 seconds. See `verification_tests.txt`.
