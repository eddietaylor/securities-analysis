"""Strategy implementations."""

from securities_analysis.strategies.base import StrategyProtocol
from securities_analysis.strategies.feature_boosted_forecast import FeatureBoostedForecastStrategy
from securities_analysis.strategies.factory import build_strategy
from securities_analysis.strategies.feature_linear_forecast import FeatureLinearForecastStrategy
from securities_analysis.strategies.mean_reversion import MeanReversionStrategy
from securities_analysis.strategies.multi_horizon_trend import MultiHorizonTrendStrategy
from securities_analysis.strategies.regime_timing_linear_forecast import RegimeTimingLinearForecastStrategy
from securities_analysis.strategies.trend_following import TimeSeriesMomentumStrategy

__all__ = [
    "StrategyProtocol",
    "TimeSeriesMomentumStrategy",
    "MultiHorizonTrendStrategy",
    "FeatureBoostedForecastStrategy",
    "FeatureLinearForecastStrategy",
    "RegimeTimingLinearForecastStrategy",
    "MeanReversionStrategy",
    "build_strategy",
]
