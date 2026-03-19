from __future__ import annotations

from dataclasses import dataclass

from securities_analysis.backtest.engine import StrategyBacktester
from securities_analysis.execution.alpaca import AlpacaTrader


@dataclass(slots=True)
class HistoricalWarmupService:
    trader: AlpacaTrader
    backtester: StrategyBacktester

    def warmup_from_history(
        self,
        symbol: str,
        asset_class: str,
        start: str,
        end: str,
        freq: str,
    ) -> int:
        bars = self.trader.get_historical_bar_objects(
            ticker=symbol,
            start=start,
            end=end,
            freq=freq,
            asset_class=asset_class,
        )
        warmed = self.backtester.warmup(bars)
        print(
            "WARMUP COMPLETE | "
            f"symbol={symbol} "
            f"bars={warmed} "
            f"start={start} "
            f"end={end} "
            f"freq={freq}"
        )
        return warmed

