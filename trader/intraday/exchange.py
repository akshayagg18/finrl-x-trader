"""CCXT OKX spot transport. External routing remains gated outside the replay engine.

Region/account eligibility must be verified separately. No withdrawal or transfer
API is exposed. This adapter does not grant permission to use account funds.
"""

import os
from datetime import UTC, datetime

from trader.brokers import AmbiguousOrder, BrokerError, MissingCredentials


class OKXSpot:
    def __init__(self, mode="paper", client=None):
        if mode not in ("paper", "live"):
            raise BrokerError("Invalid exchange mode")
        self.mode = mode
        if client is None:
            import ccxt

            prefix = "OKX_DEMO" if mode == "paper" else "OKX_LIVE"
            values = [
                os.getenv(prefix + "_" + key) for key in ("KEY", "SECRET", "PASSPHRASE")
            ]
            if not all(values):
                raise MissingCredentials(prefix + " credentials missing")
            if os.getenv("OKX_REGION_VERIFIED") != "true":
                raise BrokerError(
                    "Account region and API endpoint require verification"
                )
            client = ccxt.okx(
                {
                    "apiKey": values[0],
                    "secret": values[1],
                    "password": values[2],
                    "enableRateLimit": True,
                    "timeout": 10000,
                    "options": {"defaultType": "spot"},
                }
            )
            if mode == "paper":
                client.set_sandbox_mode(True)
        self.client = client

    def account(self):
        return self.client.fetch_balance({"type": "spot"})

    def positions(self):
        balance = self.account()
        return {k: v for k, v in balance.get("total", {}).items() if v}

    def instrument(self, symbol):
        if symbol not in ("BTC/USDT", "ETH/USDT"):
            raise BrokerError("Instrument not allowlisted")
        self.client.load_markets()
        market = self.client.market(symbol)
        if not market.get("spot") or not market.get("active"):
            raise BrokerError("Inactive or non-spot instrument")
        return market

    def quote(self, symbol):
        self.instrument(symbol)
        q = self.client.fetch_ticker(symbol)
        if not q.get("bid") or not q.get("ask") or not q.get("timestamp"):
            raise BrokerError("Incomplete quote")
        if abs(datetime.now(UTC).timestamp() * 1000 - q["timestamp"]) > 30000:
            raise BrokerError("Stale quote")
        return q

    def open_orders(self, symbol):
        return self.client.fetch_open_orders(symbol)

    def inspect(self, client_id, symbol):
        # OKX supports lookup by clOrdId through its maintained CCXT exchange binding.
        return self.client.fetch_order(None, symbol, {"clOrdId": client_id})

    def fills(self, symbol):
        return self.client.fetch_my_trades(symbol)

    def cancel(self, order_id, symbol):
        return self.client.cancel_order(order_id, symbol)

    def submit(self, *, symbol, side, quantity, client_id, authorized=False):
        if not authorized:
            raise BrokerError("External execution authorization absent")
        if side not in ("buy", "sell") or quantity <= 0:
            raise BrokerError("Invalid spot order")
        if not client_id.isalnum() or len(client_id) > 32:
            raise BrokerError("Invalid durable order identifier")
        market = self.instrument(symbol)
        amount = float(self.client.amount_to_precision(symbol, quantity))
        if amount <= 0 or amount < (
            market.get("limits", {}).get("amount", {}).get("min") or 0
        ):
            raise BrokerError("Minimum quantity")
        # Callers must durably save intent, ownership/risk permission and reconcile
        # ambiguous responses before retrying. Never retry here automatically.
        try:
            return self.client.create_order(
                symbol,
                "market",
                side,
                amount,
                None,
                {"tdMode": "cash", "clOrdId": client_id, "tgtCcy": "base_ccy"},
            )
        except Exception:  # noqa: BLE001 -- redact transport errors and mark outcome uncertain
            raise AmbiguousOrder(
                "Submission outcome uncertain; inspect durable client ID before retry"
            ) from None
