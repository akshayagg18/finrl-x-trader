"""SDK adapters, no secret storage or arbitrary URLs; only backend uses credentials."""

from typing import Protocol
import os
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass
from .data import ALLOWED


class BrokerError(RuntimeError):
    pass


class MissingCredentials(BrokerError):
    pass


class AmbiguousOrder(BrokerError):
    pass


@dataclass
class Account:
    id: str
    cash: float
    equity: float
    buying_power: float
    blocked: bool = False


@dataclass
class Instrument:
    symbol: str
    tradable: bool
    fractional: bool
    min_qty: float = 1e-6
    order_types: tuple = ("market",)


class Broker(Protocol):
    def account(self) -> Account: ...
    def positions(self) -> dict[str, float]: ...
    def open_orders(self) -> list[dict]: ...
    def instrument(self, symbol: str) -> Instrument: ...
    def market_open(self) -> bool: ...
    def quote(self, symbol: str) -> tuple[float, str]: ...
    def submit(self, order: dict) -> dict: ...
    def inspect(self, client_id: str) -> dict | None: ...
    def cancel(self, broker_id: str): ...


TERMINAL = {"filled", "canceled", "expired", "rejected", "done_for_day"}


def qty_round(qty, fractional):
    return float(
        Decimal(str(qty)).quantize(
            Decimal("0.000001") if fractional else Decimal("1"), rounding=ROUND_DOWN
        )
    )


class AlpacaBroker:
    def __init__(self, mode, client=None, data_client=None):
        if mode not in ("paper", "live"):
            raise BrokerError("Invalid Alpaca mode")
        self.mode = mode
        if client is None:
            prefix = "ALPACA_PAPER" if mode == "paper" else "ALPACA_LIVE"
            key, secret = os.getenv(prefix + "_KEY"), os.getenv(prefix + "_SECRET")
            if not key or not secret:
                raise MissingCredentials(f"{prefix} credentials not configured")
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical import StockHistoricalDataClient

            client = TradingClient(key, secret, paper=mode == "paper")
            data_client = StockHistoricalDataClient(key, secret)
            client._session.request = timeout_request(client._session.request)
        self.client, self.data_client = client, data_client

    def account(self):
        a = self.client.get_account()
        return Account(
            str(a.id),
            float(a.cash),
            float(a.equity),
            float(a.buying_power),
            bool(a.trading_blocked or a.account_blocked or a.trade_suspended_by_user),
        )

    def positions(self):
        return {p.symbol: float(p.qty) for p in self.client.get_all_positions()}

    def instrument(self, symbol):
        a = self.client.get_asset(symbol)
        return Instrument(
            symbol,
            bool(
                a.tradable
                and str(a.status).split(".")[-1].lower() == "active"
                and symbol in ALLOWED
            ),
            bool(a.fractionable),
        )

    def market_open(self):
        return bool(self.client.get_clock().is_open)

    @staticmethod
    def normalize(o):
        status = str(o.status).split(".")[-1].lower()
        return {
            "broker_id": str(o.id),
            "status": status,
            "filled_qty": float(o.filled_qty or 0),
            "fill_price": float(o.filled_avg_price or 0),
            "fees": 0.0,
            "client_id": o.client_order_id,
        }

    def open_orders(self):
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        return [
            self.normalize(o)
            for o in self.client.get_orders(
                filter=GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=500)
            )
        ]

    def inspect(self, client_id):
        from alpaca.common.exceptions import APIError

        try:
            return self.normalize(self.client.get_order_by_client_id(client_id))
        except APIError as e:
            if e.status_code == 404:
                return None
            raise BrokerError("Alpaca order lookup unavailable") from None

    def submit(self, order):
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        if not self.market_open():
            raise BrokerError(
                "Market closed: DAY fractional orders require regular session"
            )
        asset = self.instrument(order["symbol"])
        if not asset.tradable:
            raise BrokerError("Instrument unavailable")
        qty = qty_round(order["qty"], asset.fractional)
        if qty <= 0 or abs(qty - order["qty"]) > 1e-6:
            raise BrokerError("Invalid broker quantity")
        request = MarketOrderRequest(
            symbol=order["symbol"],
            qty=qty,
            side=OrderSide.BUY if order["side"] == "buy" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=order["id"],
        )
        return self.normalize(self.client.submit_order(order_data=request))

    def cancel(self, broker_id):
        self.client.cancel_order_by_id(broker_id)

    def quote(self, symbol):
        from alpaca.data.requests import StockLatestQuoteRequest
        from alpaca.data.enums import DataFeed

        q = self.data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
        )[symbol]
        if q.ask_price <= 0 or q.bid_price <= 0:
            raise BrokerError("Invalid executable quote")
        return float(q.ask_price), q.timestamp.isoformat()


def timeout_request(request):
    def wrapped(*args, **kwargs):
        kwargs.setdefault("timeout", 15)
        return request(*args, **kwargs)

    return wrapped


class IBKRBroker:
    """TWS/Gateway, one explicit account, cash USD, whole-share SMART DAY orders.
    Not auto-enabled: IBKR_CONNECTED_VERIFIED must be set after external session testing.
    """

    def __init__(self, mode, client=None):
        self.mode = mode
        self.account_id = os.getenv("IBKR_ACCOUNT", "")
        if not self.account_id:
            raise MissingCredentials("IBKR_ACCOUNT and Gateway/TWS session required")
        if mode == "paper" and not self.account_id.startswith("DU"):
            raise BrokerError("IBKR paper requires DU account")
        if mode == "live" and self.account_id.startswith("DU"):
            raise BrokerError("IBKR live cannot select DU account")
        if client is None:
            import asyncio

            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            from ib_async import IB

            client = IB()
            client.connect(
                os.getenv("IBKR_HOST", "127.0.0.1"),
                int(os.getenv("IBKR_PORT", "4002" if mode == "paper" else "4001")),
                clientId=int(os.getenv("IBKR_CLIENT_ID", "31")),
                timeout=10,
                readonly=False,
                account=self.account_id,
            )
        self.client = client
        if self.account_id not in client.managedAccounts():
            raise BrokerError("Selected IBKR account absent from session")

    def account(self):
        vals = {
            v.tag: v.value
            for v in self.client.accountSummary(self.account_id)
            if v.currency in ("USD", "")
        }
        return Account(
            self.account_id,
            float(vals["TotalCashValue"]),
            float(vals["NetLiquidation"]),
            float(vals["AvailableFunds"]),
        )

    def positions(self):
        return {
            p.contract.symbol: float(p.position)
            for p in self.client.positions(self.account_id)
        }

    def instrument(self, symbol):
        from ib_async import Stock

        contracts = self.client.qualifyContracts(Stock(symbol, "SMART", "USD"))
        return Instrument(
            symbol, bool(contracts and symbol in ALLOWED), False, min_qty=1
        )

    def market_open(self):
        from .scheduler import is_open

        return is_open()

    @staticmethod
    def normalize(t):
        statuses = {
            "Filled": "filled",
            "Cancelled": "canceled",
            "ApiCancelled": "canceled",
            "Inactive": "rejected",
            "Submitted": "accepted",
            "PreSubmitted": "accepted",
            "PendingSubmit": "pending_new",
            "PendingCancel": "pending_cancel",
        }
        fees = sum(
            float(f.commissionReport.commission)
            for f in t.fills
            if f.commissionReport and abs(float(f.commissionReport.commission)) < 1e6
        )
        return {
            "broker_id": str(t.order.orderId),
            "client_id": t.order.orderRef,
            "status": statuses.get(t.orderStatus.status, "unknown"),
            "filled_qty": float(t.orderStatus.filled),
            "fill_price": float(t.orderStatus.avgFillPrice),
            "fees": fees,
        }

    def open_orders(self):
        return [
            self.normalize(t)
            for t in self.client.reqAllOpenOrders()
            if t.order.account == self.account_id
        ]

    def inspect(self, client_id):
        trades = list(self.client.reqAllOpenOrders()) + list(
            self.client.reqCompletedOrders(apiOnly=False)
        )
        for t in trades:
            if t.order.orderRef == client_id and t.order.account == self.account_id:
                return self.normalize(t)
        # An absent order is ambiguous across Gateway resets: engine never resubmits it.
        return None

    def submit(self, order):
        from ib_async import Stock, MarketOrder

        if os.getenv("IBKR_CONNECTED_VERIFIED") != "true":
            raise BrokerError("IBKR external session verification gate is disabled")
        if not self.market_open():
            raise BrokerError("Market closed")
        if order["qty"] != int(order["qty"]):
            raise BrokerError("IBKR adapter supports whole shares only")
        contract = self.client.qualifyContracts(Stock(order["symbol"], "SMART", "USD"))[
            0
        ]
        o = MarketOrder(
            order["side"].upper(),
            int(order["qty"]),
            account=self.account_id,
            orderRef=order["id"],
            tif="DAY",
            outsideRth=False,
        )
        t = self.client.placeOrder(contract, o)
        self.client.sleep(0.5)
        return self.normalize(t)

    def cancel(self, broker_id):
        for t in self.client.reqAllOpenOrders():
            if str(t.order.orderId) == broker_id and t.order.account == self.account_id:
                self.client.cancelOrder(t.order)

    def quote(self, symbol):
        from ib_async import Stock

        t = self.client.reqTickers(
            self.client.qualifyContracts(Stock(symbol, "SMART", "USD"))[0]
        )[0]
        if not t.ask > 0 or t.time is None:
            raise BrokerError("IBKR quote/market-data entitlement unavailable")
        return float(t.ask), t.time.isoformat()


# All SDK calls stay on one dedicated worker, particularly IBKR's event loop.
from concurrent.futures import ThreadPoolExecutor

_WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="broker-session")
_SESSION = {}


def _invoke(settings, method, args, kwargs):
    key = (settings.broker, settings.mode, settings.account)
    if key not in _SESSION:
        for previous in list(_SESSION.values()):
            if isinstance(previous, IBKRBroker):
                previous.client.disconnect()
        _SESSION.clear()
        if settings.broker == "alpaca":
            _SESSION[key] = AlpacaBroker(settings.mode)
        elif settings.broker == "ibkr":
            _SESSION[key] = IBKRBroker(settings.mode)
        else:
            raise BrokerError("Use LocalBroker for simulation")
    return getattr(_SESSION[key], method)(*args, **kwargs)


class BrokerSession:
    def __init__(self, settings):
        self.settings = settings

    def __getattr__(self, method):
        if method not in (
            "account",
            "positions",
            "open_orders",
            "instrument",
            "market_open",
            "quote",
            "submit",
            "inspect",
            "cancel",
        ):
            raise AttributeError(method)

        def call(*args, **kwargs):
            return _WORKER.submit(_invoke, self.settings, method, args, kwargs).result(
                timeout=30
            )

        return call


def create_broker(settings):
    return BrokerSession(settings)
