# Free 12-week forward paper with GitHub Actions

The repository's scheduled workflow replaces an always-on laptop or paid VPS
for this credential-free experiment. A GitHub-hosted runner starts once per day,
downloads genuine completed market history and current public bid/ask quotes,
advances the persistent $500 paper account, saves a consistent SQLite snapshot
to the `forward-paper-state` branch, and shuts down.

The repository is public, so scheduled Actions usage is currently free under
GitHub's public-repository policy. GitHub can change its service, limits or
pricing. The state branch is also public; it contains public prices and virtual
positions only. **Never add broker keys, account data or other secrets to this
workflow or state branch.** `live_orders_possible` is hard false.

## Start it

1. Open the repository's **Actions** tab.
2. Select **Daily forward paper observation**.
3. Choose **Run workflow**, leave `operation=observe`, and run it on `main`.
4. Wait for the green run and inspect
   `forward-paper-state/status.json`.

The workflow also runs automatically each day at approximately **08:20
Singapore time**. GitHub explicitly does not guarantee exact cron start times;
busy periods can delay a run. A missed run is not backfilled as if it occurred
on time, and the qualification date extends when evidence is incomplete.

The first successful run creates the state branch. Healthy status contains:

```json
{
  "configured": true,
  "active": true,
  "error": null,
  "live_orders_possible": false
}
```

## Inspect progress without leaving the laptop on

Open this public status file in a browser:

<https://github.com/akshayagg18/finrl-x-trader/blob/forward-paper-state/status.json>

Or, from a local checkout:

```sh
git fetch origin forward-paper-state
git show origin/forward-paper-state:status.json
```

To inspect the saved database through the full local dashboard, first install
the application as documented in README, then make a local copy:

```sh
git fetch origin forward-paper-state
git show origin/forward-paper-state:trader.db > runtime/forward-paper-copy.db
python -m trader --db runtime/forward-paper-copy.db serve
```

This is a disposable copy. The authoritative state remains on the state branch.
Do not push manual database edits.

## Start or stop intentionally

Use **Run workflow** and choose:

- `observe`: normal idempotent daily observation.
- `stop`: marks the persistent account inactive. Scheduled jobs preserve the
  stop instead of restarting it.
- `start`: explicitly resumes the same account and attempts an observation.

The global kill and non-network data/calculation failures also remain stopped.
Only public connection and HTTP timeout classes receive automatic retries.

## Reliability boundary

This is appropriate for strategy evidence, not real brokerage execution.
GitHub Actions can be delayed or unavailable, repository Actions can be
disabled, and state-branch writes can fail. Check the Actions tab and
`status.json` at least weekly. Failed runs remain visible. Do not convert this
workflow into a live broker runner.

If it begins during the partial week starting 2 November 2026, twelve subsequent
complete Monday-to-Sunday weeks finish on 31 January 2027. The earliest honest
review is around **1 February 2027 Singapore time**, extended for missing data.
