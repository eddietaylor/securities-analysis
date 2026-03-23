from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pandas as pd
import yfinance as yf

from securities_analysis.execution.alpaca import AlpacaTrader


class HistoricalPriceProvider(Protocol):
    def get_historical_prices(
        self,
        ticker: str,
        start: str,
        end: str,
        freq: str = "day",
        asset_class: str | None = None,
    ) -> pd.DataFrame: ...


@dataclass(slots=True)
class AlpacaHistoryProvider:
    trader: AlpacaTrader

    def get_historical_prices(
        self,
        ticker: str,
        start: str,
        end: str,
        freq: str = "day",
        asset_class: str | None = None,
    ) -> pd.DataFrame:
        return self.trader.get_historical_prices(
            ticker=ticker,
            start=start,
            end=end,
            freq=freq,
            asset_class=asset_class,
        )


@dataclass(slots=True)
class YFinanceHistoryProvider:
    cache_dir: Path | None = None

    def get_historical_prices(
        self,
        ticker: str,
        start: str,
        end: str,
        freq: str = "day",
        asset_class: str | None = None,
    ) -> pd.DataFrame:
        interval = _yfinance_interval(freq)
        yf_ticker = _to_yfinance_symbol(ticker=ticker, asset_class=asset_class or "equity")
        cache_path = self._cache_path(yf_ticker=yf_ticker, start=start, end=end, freq=freq)
        if cache_path and cache_path.exists():
            frame = pd.read_csv(cache_path, parse_dates=["timestamp"]).set_index("timestamp")
            return frame

        frame = yf.download(
            yf_ticker,
            start=start,
            end=end,
            interval=interval,
            auto_adjust=False,
            progress=False,
            multi_level_index=False,
        )
        if frame.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        frame = frame.rename(columns=str.lower)
        if "adj close" in frame.columns and "close" not in frame.columns:
            frame = frame.rename(columns={"adj close": "close"})
        if "adj close" in frame.columns:
            frame = frame.drop(columns=["adj close"])
        frame.index = pd.to_datetime(frame.index, utc=True)
        frame.index.name = "timestamp"
        expected_columns = ["open", "high", "low", "close", "volume"]
        for column in expected_columns:
            if column not in frame.columns:
                frame[column] = 0.0
        frame = frame[expected_columns].sort_index()

        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            frame.reset_index().to_csv(cache_path, index=False)
        return frame

    def _cache_path(self, *, yf_ticker: str, start: str, end: str, freq: str) -> Path | None:
        if self.cache_dir is None:
            return None
        safe_symbol = yf_ticker.replace("/", "_").replace("^", "caret_").replace("=", "_")
        return self.cache_dir / f"{safe_symbol}_{start}_{end}_{freq}.csv"


def build_history_provider(
    *,
    history_provider: str,
    trader: AlpacaTrader | None = None,
    cache_dir: str | Path | None = None,
) -> HistoricalPriceProvider:
    if history_provider == "alpaca":
        if trader is None:
            raise ValueError("Alpaca history provider requires a trader instance.")
        return AlpacaHistoryProvider(trader=trader)
    if history_provider == "yfinance":
        resolved_cache = Path(cache_dir) if cache_dir else Path("artifacts") / "data_cache" / "yfinance"
        resolved_cache.mkdir(parents=True, exist_ok=True)
        tz_cache_dir = resolved_cache / "tz_cache"
        tz_cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            yf.set_tz_cache_location(str(tz_cache_dir))
        except AttributeError:
            pass
        return YFinanceHistoryProvider(cache_dir=resolved_cache)
    raise ValueError(f"Unknown history provider: {history_provider}")


def _to_yfinance_symbol(*, ticker: str, asset_class: str) -> str:
    if asset_class == "crypto":
        return ticker.replace("/", "-")
    if asset_class == "future":
        return ticker
    return ticker


def _yfinance_interval(freq: str) -> str:
    mapping = {
        "day": "1d",
        "week": "1wk",
        "month": "1mo",
        "hour": "1h",
        "minute": "1m",
    }
    if freq not in mapping:
        raise KeyError(f"Unsupported yfinance frequency: {freq}")
    return mapping[freq]
