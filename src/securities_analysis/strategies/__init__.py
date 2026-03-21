"""Strategy implementations."""

from securities_analysis.strategies.base import StrategyProtocol
from securities_analysis.strategies.factory import build_strategy
from securities_analysis.strategies.mean_reversion import MeanReversionStrategy
from securities_analysis.strategies.multi_horizon_trend import MultiHorizonTrendStrategy
from securities_analysis.strategies.trend_following import TimeSeriesMomentumStrategy

__all__ = [
    "StrategyProtocol",
    "TimeSeriesMomentumStrategy",
    "MultiHorizonTrendStrategy",
    "MeanReversionStrategy",
    "build_strategy",
]
