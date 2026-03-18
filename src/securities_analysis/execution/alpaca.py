from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from typing import Any, Callable

import pandas as pd
from alpaca.data import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.live.crypto import CryptoDataStream
from alpaca.data.live.stock import StockDataStream
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestQuoteRequest
from alpaca.data.requests import StockBarsRequest, StockLatestQuoteRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetExchange, AssetStatus
from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import GetAssetsRequest, GetOrdersRequest
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from alpaca.trading.requests import StopLimitOrderRequest, StopOrderRequest
from alpaca.trading.requests import TrailingStopOrderRequest

from securities_analysis.agents.contracts import Bar, MarketEvent, OrderIntent
from securities_analysis.agents.contracts import OrderRecord, OrderType as IntentOrderType
from securities_analysis.agents.contracts import PositionSnapshot, Side
from securities_analysis.config import AlpacaSettings, load_alpaca_settings


AssetClassName = str
BarHandler = Callable[[Bar], None]
QuoteHandler = Callable[[MarketEvent], None]


class AlpacaTrader:
    """Package-based wrapper around the alpaca-py SDK."""

    def __init__(self, settings: AlpacaSettings):
        self.settings = settings
        self.crypto_client = CryptoHistoricalDataClient()
        self.stock_client = StockHistoricalDataClient(
            settings.api_key,
            settings.secret_key,
        )
        trading_client_kwargs: dict[str, Any] = {"paper": settings.paper}
        if settings.endpoint:
            trading_client_kwargs["url_override"] = settings.endpoint
        self.trading_client = TradingClient(
            settings.api_key,
            settings.secret_key,
            **trading_client_kwargs,
        )
        self._buffer: deque[MarketEvent] = deque()
        self._interval_end: datetime | None = None

    @classmethod
    def from_cfg(cls, path: str) -> "AlpacaTrader":
        return cls(load_alpaca_settings(cfg_path=path))

    @classmethod
    def from_env(cls) -> "AlpacaTrader":
        return cls(load_alpaca_settings())

    def get_current_price(
        self,
        ticker: str,
        asset_class: AssetClassName = "equity",
    ) -> tuple[datetime, float, float]:
        if asset_class == "equity":
            request = StockLatestQuoteRequest(symbol_or_symbols=[ticker])
            latest_quote = self.stock_client.get_stock_latest_quote(request)
        else:
            request = CryptoLatestQuoteRequest(symbol_or_symbols=[ticker])
            latest_quote = self.crypto_client.get_crypto_latest_quote(request)

        quote = latest_quote[ticker]
        return quote.timestamp, float(quote.bid_price), float(quote.ask_price)

    def get_historical_prices(
        self,
        ticker: str,
        start: str,
        end: str,
        freq: str = "day",
        asset_class: AssetClassName | None = None,
    ) -> pd.DataFrame:
        timeframe_map = {
            "minute": TimeFrame.Minute,
            "hour": TimeFrame.Hour,
            "day": TimeFrame.Day,
            "week": TimeFrame.Week,
            "month": TimeFrame.Month,
        }
        resolved_asset_class = asset_class or self._infer_asset_class(ticker)
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        end_dt = datetime.strptime(end, "%Y-%m-%d")

        if resolved_asset_class == "equity":
            request = StockBarsRequest(
                symbol_or_symbols=[ticker],
                timeframe=timeframe_map[freq],
                start=start_dt,
                end=end_dt,
            )
            return self.stock_client.get_stock_bars(request).df

        request = CryptoBarsRequest(
            symbol_or_symbols=[ticker],
            timeframe=timeframe_map[freq],
            start=start_dt,
            end=end_dt,
        )
        return self.crypto_client.get_crypto_bars(request).df

    def get_historical_bar_objects(
        self,
        ticker: str,
        start: str,
        end: str,
        freq: str = "day",
        asset_class: AssetClassName | None = None,
    ) -> list[Bar]:
        bars_df = self.get_historical_prices(
            ticker=ticker,
            start=start,
            end=end,
            freq=freq,
            asset_class=asset_class,
        )
        return self._bars_from_dataframe(ticker=ticker, bars_df=bars_df)

    def stream_quotes(
        self,
        ticker: str,
        asset_class: AssetClassName,
        interval_seconds: int = 60,
        on_bar: BarHandler | None = None,
        on_quote: QuoteHandler | None = None,
    ) -> None:
        stream = self._build_stream(asset_class=asset_class)

        async def quote_handler(data: Any) -> None:
            market_event = self._to_market_event(ticker=ticker, data=data)
            if on_quote:
                on_quote(market_event)
            bar = self._update_buffer(market_event, interval_seconds)
            if bar and on_bar:
                on_bar(bar)

        stream.subscribe_quotes(quote_handler, ticker)
        stream.run()

    def get_account_details(self) -> Any:
        return self.trading_client.get_account()

    def get_available_assets(
        self,
        asset_class: AssetClassName = "equity",
        status: str = "active",
        exchange: str = "nyse",
    ) -> pd.DataFrame | None:
        asset_map = {
            "equity": AssetClass.US_EQUITY,
            "crypto": AssetClass.CRYPTO,
        }
        status_map = {
            "active": AssetStatus.ACTIVE,
            "inactive": AssetStatus.INACTIVE,
        }
        exchange_map = {
            "amex": AssetExchange.AMEX,
            "arca": AssetExchange.ARCA,
            "bats": AssetExchange.BATS,
            "nyse": AssetExchange.NYSE,
            "nasdaq": AssetExchange.NASDAQ,
            "nysearca": AssetExchange.NYSEARCA,
            "ftxu": AssetExchange.FTXU,
            "cbse": AssetExchange.CBSE,
            "gnss": AssetExchange.GNSS,
            "ersx": AssetExchange.ERSX,
            "otc": AssetExchange.OTC,
        }
        request = GetAssetsRequest(
            asset_class=asset_map[asset_class],
            status=status_map[status],
            exchange=exchange_map[exchange],
        )
        assets = self.trading_client.get_all_assets(request)
        return self._records_to_frame(assets)

    def create_order(
        self,
        ticker: str,
        units: float | None = None,
        qty_price: float | None = None,
        order_type: str = "market",
        limit_price: float | None = None,
        stop_price: float | None = None,
        trail_price: float | None = None,
        trail_perc: float | None = None,
        side: str = "buy",
        time_in_force: str = "day",
    ) -> Any:
        side_map = {
            "buy": OrderSide.BUY,
            "sell": OrderSide.SELL,
        }
        tif_map = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
        }

        if order_type == "market":
            request = MarketOrderRequest(
                symbol=ticker,
                qty=units,
                notional=qty_price,
                side=side_map[side],
                time_in_force=tif_map[time_in_force],
            )
        elif order_type == "limit":
            request = LimitOrderRequest(
                symbol=ticker,
                qty=units,
                limit_price=limit_price,
                side=side_map[side],
                time_in_force=tif_map[time_in_force],
            )
        elif order_type == "stop":
            request = StopOrderRequest(
                symbol=ticker,
                qty=units,
                stop_price=stop_price,
                side=side_map[side],
                time_in_force=tif_map[time_in_force],
                type=OrderType.STOP,
            )
        elif order_type == "stop_limit":
            request = StopLimitOrderRequest(
                symbol=ticker,
                qty=units,
                stop_price=stop_price,
                limit_price=limit_price,
                side=side_map[side],
                time_in_force=tif_map[time_in_force],
                type=OrderType.STOP_LIMIT,
            )
        elif order_type == "trailing_stop":
            trailing_kwargs: dict[str, Any] = {
                "symbol": ticker,
                "qty": units,
                "side": side_map[side],
                "time_in_force": tif_map[time_in_force],
                "type": OrderType.TRAILING_STOP,
            }
            if trail_price is not None:
                trailing_kwargs["trail_price"] = trail_price
            if trail_perc is not None:
                trailing_kwargs["trail_percent"] = trail_perc
            request = TrailingStopOrderRequest(**trailing_kwargs)
        else:
            raise ValueError(f"Unsupported order_type: {order_type}")

        return self.trading_client.submit_order(order_data=request)

    def submit_order_intent(self, intent: OrderIntent) -> Any:
        return self.create_order(
            ticker=intent.symbol,
            units=intent.quantity,
            qty_price=intent.notional,
            order_type=intent.order_type.value,
            limit_price=intent.limit_price,
            stop_price=intent.stop_price,
            trail_perc=intent.trail_percent,
            side=intent.side.value,
            time_in_force=intent.time_in_force,
        )

    def get_orders(self, status: str = "all", side: str = "all") -> pd.DataFrame | None:
        request_kwargs: dict[str, Any] = {"status": status}
        if side != "all":
            request_kwargs["side"] = side
        orders = self.trading_client.get_orders(filter=GetOrdersRequest(**request_kwargs))
        return self._records_to_frame(orders)

    def cancel_all_orders(self) -> Any:
        return self.trading_client.cancel_orders()

    def get_all_positions(self) -> pd.DataFrame | None:
        positions = self.trading_client.get_all_positions()
        return self._records_to_frame(positions)

    def get_position_quantity(self, symbol: str) -> float:
        for position in self.trading_client.get_all_positions():
            if position.symbol == symbol:
                return float(position.qty)
        return 0.0

    def get_position_snapshots(self) -> list[PositionSnapshot]:
        snapshots: list[PositionSnapshot] = []
        for position in self.trading_client.get_all_positions():
            snapshots.append(
                PositionSnapshot(
                    symbol=position.symbol,
                    snapshot_time=datetime.utcnow(),
                    quantity=float(position.qty),
                    market_value=self._safe_float(position.market_value),
                    average_entry_price=self._safe_float(position.avg_entry_price),
                    unrealized_pnl=self._safe_float(position.unrealized_pl),
                )
            )
        return snapshots

    def close_all_positions(self, cancel_orders: bool = True) -> Any:
        return self.trading_client.close_all_positions(cancel_orders=cancel_orders)

    def order_to_record(self, order: Any) -> OrderRecord:
        return OrderRecord(
            broker_order_id=str(order.id),
            symbol=order.symbol,
            submitted_at=order.submitted_at or datetime.utcnow(),
            status=str(order.status),
            side=Side(str(order.side)),
            order_type=IntentOrderType(str(order.type)),
            requested_quantity=self._safe_float(getattr(order, "qty", None)),
            filled_quantity=self._safe_float(getattr(order, "filled_qty", None)),
            average_fill_price=self._safe_float(getattr(order, "filled_avg_price", None)),
        )

    def _build_stream(self, asset_class: AssetClassName) -> StockDataStream | CryptoDataStream:
        if asset_class == "equity":
            return StockDataStream(self.settings.api_key, self.settings.secret_key)
        if asset_class == "crypto":
            return CryptoDataStream(self.settings.api_key, self.settings.secret_key)
        raise ValueError(f"Unsupported asset_class: {asset_class}")

    def _to_market_event(self, ticker: str, data: Any) -> MarketEvent:
        raw = self._to_dict(data)
        return MarketEvent(
            symbol=ticker,
            event_time=getattr(data, "timestamp", datetime.utcnow()),
            bid_price=self._safe_float(getattr(data, "bid_price", None)),
            ask_price=self._safe_float(getattr(data, "ask_price", None)),
            bid_size=self._safe_float(getattr(data, "bid_size", None)),
            ask_size=self._safe_float(getattr(data, "ask_size", None)),
            source="alpaca",
            raw=raw,
        )

    def _update_buffer(self, event: MarketEvent, interval_seconds: int) -> Bar | None:
        self._buffer.append(event)
        if self._interval_end is None:
            self._interval_end = event.event_time + timedelta(seconds=interval_seconds)
            return None

        if event.event_time < self._interval_end:
            return None

        bar = self._aggregate_buffer()
        self._buffer.clear()
        self._buffer.append(event)
        self._interval_end = event.event_time + timedelta(seconds=interval_seconds)
        return bar

    def _aggregate_buffer(self) -> Bar | None:
        prices = [item.bid_price for item in self._buffer if item.bid_price is not None]
        if not prices:
            return None

        events = [item for item in self._buffer if item.bid_price is not None]
        return Bar(
            symbol=events[0].symbol,
            start_time=events[0].event_time,
            end_time=events[-1].event_time,
            open_price=float(prices[0]),
            high_price=float(max(prices)),
            low_price=float(min(prices)),
            close_price=float(prices[-1]),
        )

    @staticmethod
    def _bars_from_dataframe(ticker: str, bars_df: pd.DataFrame) -> list[Bar]:
        if bars_df.empty:
            return []

        frame = bars_df.reset_index()
        timestamp_column = "timestamp"
        if timestamp_column not in frame.columns:
            raise KeyError("Historical bars dataframe is missing a timestamp column")

        bars: list[Bar] = []
        for row in frame.itertuples(index=False):
            timestamp = getattr(row, timestamp_column)
            open_price = float(getattr(row, "open"))
            high_price = float(getattr(row, "high"))
            low_price = float(getattr(row, "low"))
            close_price = float(getattr(row, "close"))
            volume = AlpacaTrader._safe_float(getattr(row, "volume", None))
            bars.append(
                Bar(
                    symbol=ticker,
                    start_time=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                    end_time=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    volume=volume,
                    source="alpaca_historical",
                )
            )
        return bars

    @staticmethod
    def _records_to_frame(records: list[Any]) -> pd.DataFrame | None:
        if not records:
            return None
        return pd.DataFrame.from_records([AlpacaTrader._to_dict(item) for item in records])

    @staticmethod
    def _infer_asset_class(ticker: str) -> AssetClassName:
        return "crypto" if "/" in ticker else "equity"

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _to_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "dict"):
            return value.dict()
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        raise TypeError(f"Cannot convert {type(value)!r} to dict")


tradeAlpaca = AlpacaTrader
