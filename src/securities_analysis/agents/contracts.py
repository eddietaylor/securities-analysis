from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    MARKET_DATA = "market_data"
    STRATEGY = "strategy"
    RISK = "risk"
    EXECUTION = "execution"
    BACKTEST = "backtest"
    OPS = "ops"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


@dataclass(slots=True)
class MarketEvent:
    symbol: str
    event_time: datetime
    bid_price: float | None = None
    ask_price: float | None = None
    last_price: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    source: str = "alpaca"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Bar:
    symbol: str
    start_time: datetime
    end_time: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float | None = None
    source: str = "aggregated_quotes"


@dataclass(slots=True)
class SignalDecision:
    symbol: str
    decision_time: datetime
    signal_name: str
    target_position: float
    confidence: float | None = None
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class HorizonForecast:
    horizon_bars: int
    expected_return: float
    signal_strength: float
    weight: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ForecastSnapshot:
    symbol: str
    forecast_time: datetime
    model_name: str
    aggregate_expected_return: float
    aggregate_score: float
    realized_volatility: float | None = None
    confidence: float | None = None
    regime_label: str = ""
    horizons: list[HorizonForecast] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderIntent:
    symbol: str
    created_at: datetime
    side: Side
    order_type: OrderType
    quantity: float | None = None
    notional: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    trail_percent: float | None = None
    time_in_force: str = "day"
    strategy_id: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class OrderRecord:
    broker_order_id: str
    symbol: str
    submitted_at: datetime
    status: str
    side: Side
    order_type: OrderType
    requested_quantity: float | None = None
    filled_quantity: float | None = None
    average_fill_price: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PositionSnapshot:
    symbol: str
    snapshot_time: datetime
    quantity: float
    market_value: float | None = None
    average_entry_price: float | None = None
    unrealized_pnl: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
