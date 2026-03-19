from __future__ import annotations

from securities_analysis.strategies.base import StrategyProtocol
from securities_analysis.strategies.mean_reversion import MeanReversionStrategy
from securities_analysis.strategies.trend_following import TimeSeriesMomentumStrategy


def build_strategy(
    strategy_family: str,
    symbol: str,
    lookback_bars: int,
    vol_lookback_bars: int,
    target_volatility: float,
    max_gross_leverage: float,
    periods_per_year: int,
    allow_short: bool,
    mean_reversion_entry_zscore: float = 1.0,
    mean_reversion_exit_zscore: float = 0.25,
) -> StrategyProtocol:
    min_bars = max(lookback_bars, vol_lookback_bars) + 5
    if strategy_family == "trend":
        return TimeSeriesMomentumStrategy(
            symbol=symbol,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            target_volatility=target_volatility,
            max_gross_leverage=max_gross_leverage,
            periods_per_year=periods_per_year,
            min_bars=min_bars,
            long_only=not allow_short,
        )
    if strategy_family == "mean_reversion":
        return MeanReversionStrategy(
            symbol=symbol,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            target_volatility=target_volatility,
            max_gross_leverage=max_gross_leverage,
            periods_per_year=periods_per_year,
            min_bars=min_bars,
            long_only=not allow_short,
            entry_zscore=mean_reversion_entry_zscore,
            exit_zscore=mean_reversion_exit_zscore,
        )
    raise ValueError(f"Unsupported strategy family: {strategy_family}")
