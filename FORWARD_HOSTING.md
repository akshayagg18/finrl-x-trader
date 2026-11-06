# Always-on 12-week forward-paper hosting

The forward-paper record needs an internet-connected process, but it does not
need to run on a laptop. Use a small Ubuntu VPS that stays powered by the cloud
provider. The service uses public market data only; broker credentials are not
needed and `live_orders_possible` remains false.

## Recommended host

Create a small **Ubuntu 24.04 LTS** VPS with at least 1 GB RAM, 15 GB disk and a
public IPv4 address. Two GB RAM gives more installation headroom. Choose a
Singapore or nearby region when available. A basic instance typically costs a
few U.S. dollars per month; verify the provider's current price before creating
it. Oracle's free tier can work when capacity is available, but a small paid VPS
is simpler and more predictable for an uninterrupted experiment.

Add your SSH public key during server creation. Do not add broker keys. The
application dashboard stays bound to the server's loopback interface and is not
publicly exposed.

## Install

Connect to the new server using the username supplied by the provider, commonly
`ubuntu`:

```sh
ssh ubuntu@SERVER_IP
```

On the server:

```sh
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/akshayagg18/finrl-x-trader.git
sudo bash finrl-x-trader/deploy/install_forward_ubuntu.sh
```

The installer creates a locked-down `finrl` system user, installs Python
dependencies under `/opt/finrl-x-trader`, initializes the private SQLite state,
activates the frozen $500 forward-paper account, and enables these systemd
units:

- `finrl-forward.service`: private dashboard and ten-second persistent scheduler.
- `finrl-forward-watchdog.timer`: hourly public-data health check. It retries
  connection/HTTP timeouts, but respects an intentional Stop, global kill,
  stale data or calculation failure.
- `finrl-forward-backup.timer`: daily consistent SQLite backup with 30-copy
  rotation.

The service restarts after a crash or server reboot. A VPS does not enter laptop
sleep mode. Provider maintenance or network outages remain possible and appear
in the audit record.

## Open the private dashboard

Keep this command running on the laptop while inspecting the dashboard:

```sh
ssh -L 8765:127.0.0.1:8765 ubuntu@SERVER_IP
```

Open <http://127.0.0.1:8765>. Closing the SSH window closes only the viewing
tunnel; the server process continues running.

## Check health

Run on the VPS:

```sh
sudo systemctl status finrl-forward --no-pager
sudo systemctl list-timers 'finrl-forward-*'
sudo -u finrl /opt/finrl-x-trader/.venv/bin/python \
  -m scripts.forward_status \
  --db /opt/finrl-x-trader/runtime/trader.db
sudo journalctl -u finrl-forward -n 100 --no-pager
```

Healthy state shows `configured: true`, `active: true`, no error, increasing
observation counts, and `live_orders_possible: false`.

Use the dashboard **Stop** control when you intend to stop the experiment. The
watchdog does not override an intentional stop. The global kill also blocks
watchdog recovery.

## Backups

Backups are stored in
`/opt/finrl-x-trader/runtime/backups/forward-<UTC timestamp>.db`. They protect
against application/database mistakes but remain on the same VPS disk. Download
one weekly for off-host protection:

```sh
# On the VPS, replace BACKUP_FILE with the newest filename.
sudo cp /opt/finrl-x-trader/runtime/backups/BACKUP_FILE /tmp/forward-backup.db
sudo chown "$USER":"$USER" /tmp/forward-backup.db

# On the laptop:
scp ubuntu@SERVER_IP:/tmp/forward-backup.db .
```

Do not use `rm -rf /opt/finrl-x-trader`, delete the SQLite database, or rerun
with a different database path during the 12-week record. The observation
timestamps, downtime and errors are part of the evidence and should remain
visible.

## Earliest review date

If the first observation is recorded during the partial week beginning
2 November 2026, twelve subsequent complete Monday-to-Sunday weeks finish on
31 January 2027. The earliest honest assessment is therefore around
**1 February 2027 Singapore time**. Missing observations can extend this date.
