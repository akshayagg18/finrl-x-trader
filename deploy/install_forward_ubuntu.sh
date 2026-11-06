#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

APP_DIR=/opt/finrl-x-trader
APP_USER=finrl
REPO_URL=${FINRL_REPO_URL:-https://github.com/akshayagg18/finrl-x-trader.git}

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends git python3 python3-venv ca-certificates

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /var/lib/finrl --shell /usr/sbin/nologin "$APP_USER"
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone --depth 1 "$REPO_URL" "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
else
  runuser -u "$APP_USER" -- git -C "$APP_DIR" pull --ff-only
fi

runuser -u "$APP_USER" -- python3 -m venv "$APP_DIR/.venv"
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements-app.txt"
install -d -o "$APP_USER" -g "$APP_USER" -m 0700 "$APP_DIR/runtime" "$APP_DIR/runtime/backups"

for unit in "$APP_DIR"/deploy/systemd/finrl-forward*; do
  install -m 0644 "$unit" "/etc/systemd/system/$(basename "$unit")"
done

runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" -m trader --db "$APP_DIR/runtime/trader.db" init
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" -m scripts.start_defensive_forward --db "$APP_DIR/runtime/trader.db" --capital 500 --defer-observation

systemctl daemon-reload
systemctl enable --now finrl-forward.service
systemctl enable --now finrl-forward-watchdog.timer
systemctl enable --now finrl-forward-backup.timer

cat <<'EOF'

FinRL-X forward paper is installed and will survive logout and server reboot.
The dashboard is deliberately private on the server's 127.0.0.1:8765.

From your laptop, open an SSH tunnel (replace SERVER_IP):
  ssh -L 8765:127.0.0.1:8765 YOUR_SERVER_USER@SERVER_IP

Then open http://127.0.0.1:8765 locally.

Server health:
  sudo systemctl status finrl-forward --no-pager
  sudo -u finrl /opt/finrl-x-trader/.venv/bin/python -m scripts.forward_status --db /opt/finrl-x-trader/runtime/trader.db

Logs:
  sudo journalctl -u finrl-forward -f
EOF
