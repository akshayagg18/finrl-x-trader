# Forward-host deployment verification

- `bash -n deploy/install_forward_ubuntu.sh` passed.
- Ruff passed for the API change, watchdog, backup command, activation command
  and deployment tests.
- `systemd-analyze verify` parsed all five unit files. On this development host
  it reported only that `/opt/finrl-x-trader/.venv/bin/python` is absent; that
  path is deliberately created by the installer before the units are enabled.
- Automated tests verify intentional Stop and global kill are preserved,
  transient network errors alone are retried, retry events are audited, SQLite
  backups pass `PRAGMA integrity_check`, and retention deletes older copies.
- The full application regression result is retained in
  `deploy/verification_tests.txt`: **111 passed**, 5,078 dependency
  deprecation warnings in 63.42 seconds.

External verification still required: provision a real Ubuntu 24.04 VPS under
the user's cloud account, run the installer, inspect the first persisted public
observation, reboot the VPS once, confirm service/timer recovery, and download
one backup through the documented SSH workflow. No cloud credentials or server
were available during repository development.
