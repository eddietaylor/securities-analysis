from __future__ import annotations

from securities_analysis.strategies.base import StrategyProtocol
from securities_analysis.strategies.feature_boosted_forecast import FeatureBoostedForecastStrategy
from securities_analysis.strategies.feature_linear_forecast import FeatureLinearForecastStrategy
from securities_analysis.strategies.mean_reversion import MeanReversionStrategy
from securities_analysis.strategies.multi_horizon_trend import MultiHorizonTrendStrategy
from securities_analysis.strategies.regime_timing_linear_forecast import RegimeTimingLinearForecastStrategy
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
    max_train_samples: int | None = None,
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
    if strategy_family == "multi_horizon_trend":
        return MultiHorizonTrendStrategy(
            symbol=symbol,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            target_volatility=target_volatility,
            max_gross_leverage=max_gross_leverage,
            periods_per_year=periods_per_year,
            min_bars=min_bars,
            long_only=not allow_short,
        )
    if strategy_family == "feature_linear_forecast":
        return FeatureLinearForecastStrategy(
            symbol=symbol,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            target_volatility=target_volatility,
            max_gross_leverage=max_gross_leverage,
            periods_per_year=periods_per_year,
            min_bars=max(min_bars, lookback_bars + 30),
            long_only=not allow_short,
            max_train_samples=max_train_samples,
        )
    if strategy_family == "feature_boosted_forecast":
        return FeatureBoostedForecastStrategy(
            symbol=symbol,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            target_volatility=target_volatility,
            max_gross_leverage=max_gross_leverage,
            periods_per_year=periods_per_year,
            min_bars=max(min_bars, lookback_bars + 60),
            long_only=not allow_short,
            max_train_samples=max_train_samples,
        )
    if strategy_family == "regime_timing_linear_forecast":
        return RegimeTimingLinearForecastStrategy(
            symbol=symbol,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            target_volatility=target_volatility,
            max_gross_leverage=max_gross_leverage,
            periods_per_year=periods_per_year,
            min_bars=max(min_bars, lookback_bars + 30),
            long_only=not allow_short,
            max_train_samples=max_train_samples,
        )
    raise ValueError(f"Unsupported strategy family: {strategy_family}")
