from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from securities_analysis.agents.contracts import Bar, ForecastSnapshot, HorizonForecast, SignalDecision


@dataclass(slots=True)
class MultiHorizonTrendStrategy:
    """Multi-horizon trend forecaster with agreement-aware vol-scaled positioning."""

    symbol: str
    lookback_bars: int = 60
    vol_lookback_bars: int = 20
    target_volatility: float = 0.15
    max_gross_leverage: float = 1.0
    periods_per_year: int = 252
    min_bars: int = 65
    long_only: bool = True
    bars: deque[Bar] = field(default_factory=deque)
    asset_returns: deque[float] = field(default_factory=deque)
    strategy_returns: deque[float] = field(default_factory=deque)
    current_target_position: float = 0.0
    latest_forecast: ForecastSnapshot | None = None

    def on_bar(self, bar: Bar) -> SignalDecision | None:
        self._append_bar(bar)
        if len(self.bars) < self.min_bars:
            return None

        closes = np.array([item.close_price for item in self.bars], dtype=float)
        returns = np.diff(np.log(closes))
        if len(returns) < max(self.lookback_bars, self.vol_lookback_bars):
            return None

        realized_vol = float(np.std(returns[-self.vol_lookback_bars :], ddof=1) * np.sqrt(self.periods_per_year))
        horizons = self._horizons()

        horizon_forecasts: list[HorizonForecast] = []
        weighted_score = 0.0
        weighted_expected_return = 0.0
        weight_total = 0.0
        directions: list[float] = []

        for horizon_bars, weight in horizons:
            horizon_window = returns[-horizon_bars:]
            horizon_mean = float(np.mean(horizon_window))
            horizon_std = float(np.std(horizon_window, ddof=1))
            cumulative_return = float(np.sum(horizon_window))
            signal_strength = cumulative_return / max(horizon_std, 1e-8)
            expected_return = horizon_mean * horizon_bars
            direction = float(np.sign(signal_strength))

            horizon_forecasts.append(
                HorizonForecast(
                    horizon_bars=horizon_bars,
                    expected_return=expected_return,
                    signal_strength=signal_strength,
                    weight=weight,
                    metadata={
                        "mean_return": horizon_mean,
                        "cumulative_return": cumulative_return,
                        "direction": direction,
                    },
                )
            )
            weighted_score += weight * signal_strength
            weighted_expected_return += weight * expected_return
            weight_total += weight
            directions.append(direction)

        aggregate_score = weighted_score / max(weight_total, 1e-8)
        aggregate_expected_return = weighted_expected_return / max(weight_total, 1e-8)
        aggregate_direction = float(np.sign(aggregate_score))
        agreement_ratio = (
            float(np.mean([1.0 if direction == aggregate_direction and direction != 0 else 0.0 for direction in directions]))
            if aggregate_direction != 0
            else 0.0
        )
        confidence = float(min(abs(aggregate_score) / 4.0, 1.0) * max(agreement_ratio, 0.25))

        direction = aggregate_direction
        if self.long_only and direction < 0:
            direction = 0.0

        volatility_scalar = self.target_volatility / max(realized_vol, 1e-6)
        directional_scalar = min(abs(aggregate_score) / 3.0, 1.0)
        raw_target = direction * min(volatility_scalar * directional_scalar * max(agreement_ratio, 0.25), self.max_gross_leverage)
        target_position = float(np.clip(raw_target, -self.max_gross_leverage, self.max_gross_leverage))
        if self.long_only and target_position < 0:
            target_position = 0.0

        latest_return = float(returns[-1])
        self.asset_returns.append(latest_return)
        self.strategy_returns.append(latest_return * self.current_target_position)
        self.current_target_position = target_position

        regime_label = self._regime_label(aggregate_score, agreement_ratio, target_position)
        rationale = (
            f"aggregate_score={aggregate_score:.4f}, "
            f"agreement_ratio={agreement_ratio:.3f}, "
            f"realized_vol={realized_vol:.4f}, "
            f"target_position={target_position:.4f}"
        )
        self.latest_forecast = ForecastSnapshot(
            symbol=self.symbol,
            forecast_time=bar.end_time,
            model_name="multi_horizon_trend",
            aggregate_expected_return=aggregate_expected_return,
            aggregate_score=aggregate_score,
            realized_volatility=realized_vol,
            confidence=confidence,
            regime_label=regime_label,
            horizons=horizon_forecasts,
            metadata={
                "agreement_ratio": agreement_ratio,
                "target_position": target_position,
                "close_price": bar.close_price,
            },
        )

        horizon_metadata = {
            f"h{forecast.horizon_bars}_expected_return": forecast.expected_return
            for forecast in horizon_forecasts
        }
        horizon_metadata.update(
            {
                f"h{forecast.horizon_bars}_signal_strength": forecast.signal_strength
                for forecast in horizon_forecasts
            }
        )
        horizon_metadata.update(
            {
                "aggregate_expected_return": aggregate_expected_return,
                "aggregate_score": aggregate_score,
                "agreement_ratio": agreement_ratio,
                "realized_volatility": realized_vol,
                "close_price": bar.close_price,
                "regime_label": regime_label,
            }
        )

        return SignalDecision(
            symbol=self.symbol,
            decision_time=bar.end_time,
            signal_name="multi_horizon_trend",
            target_position=target_position,
            confidence=confidence,
            rationale=rationale,
            metadata=horizon_metadata,
        )

    def get_strategy_returns(self) -> np.ndarray:
        return np.array(self.strategy_returns, dtype=float)

    def get_asset_returns(self) -> np.ndarray:
        return np.array(self.asset_returns, dtype=float)

    def get_latest_forecast(self) -> ForecastSnapshot | None:
        return self.latest_forecast

    def _append_bar(self, bar: Bar) -> None:
        max_bars = max(self.min_bars, self.lookback_bars, self.vol_lookback_bars) + 5
        self.bars.append(bar)
        while len(self.bars) > max_bars:
            self.bars.popleft()

    def _horizons(self) -> list[tuple[int, float]]:
        short_horizon = max(5, self.lookback_bars // 4)
        medium_horizon = max(short_horizon + 1, self.lookback_bars // 2)
        horizons = sorted({short_horizon, medium_horizon, self.lookback_bars})
        weights = np.array([1.0, 1.5, 2.0], dtype=float)[-len(horizons) :]
        normalized = weights / np.sum(weights)
        return list(zip(horizons, normalized.tolist(), strict=True))

    @staticmethod
    def _regime_label(aggregate_score: float, agreement_ratio: float, target_position: float) -> str:
        if target_position <= 0:
            return "flat_or_untrusted"
        if agreement_ratio >= 0.99 and aggregate_score > 0:
            return "aligned_uptrend"
        if agreement_ratio >= 0.66 and aggregate_score > 0:
            return "partially_aligned_uptrend"
        return "weak_uptrend"
