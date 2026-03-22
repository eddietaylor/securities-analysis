from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from securities_analysis.agents.contracts import Bar, ForecastSnapshot, HorizonForecast, SignalDecision


@dataclass(slots=True)
class MultiHorizonTrendStrategy:
    """Multi-horizon trend forecaster with regime gating and timing confirmation."""

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

        horizon_features: list[tuple[int, float, dict[str, float]]] = []
        for horizon_bars, _weight in horizons:
            horizon_features.append((horizon_bars, *self._horizon_features(returns, horizon_bars)))

        short_horizon = horizons[0][0]
        medium_horizon = horizons[1][0]
        long_horizon = horizons[-1][0]

        feature_by_horizon = {
            horizon: {"score": score, **metadata}
            for horizon, score, metadata in horizon_features
        }

        short_score = feature_by_horizon[short_horizon]["score"]
        medium_score = feature_by_horizon[medium_horizon]["score"]
        long_score = feature_by_horizon[long_horizon]["score"]

        timing_score = float(0.65 * short_score + 0.35 * medium_score)
        regime_strength = float(np.tanh(long_score / 2.0))
        timing_strength = float(np.tanh(timing_score / 2.0))

        long_direction = float(np.sign(long_score))
        short_direction = float(np.sign(short_score))
        medium_direction = float(np.sign(medium_score))

        agreement_ratio = float(
            np.mean(
                [
                    1.0 if direction == long_direction and direction != 0.0 else 0.0
                    for direction in (short_direction, medium_direction)
                ]
            )
        ) if long_direction != 0.0 else 0.0

        regime_active = bool(long_score > 0.25)
        timing_active = bool(timing_score > 0.10)
        pullback_penalty = 0.5 if short_score < 0 < medium_score and regime_active else 1.0

        if regime_active and timing_active:
            direction = 1.0
        else:
            direction = 0.0 if self.long_only else float(np.sign(timing_score))

        if self.long_only and direction < 0:
            direction = 0.0

        aggregate_score = float(0.60 * regime_strength + 0.40 * timing_strength)
        aggregate_expected_return = float(
            realized_vol
            * np.sqrt(long_horizon / max(self.periods_per_year, 1))
            * aggregate_score
            * max(agreement_ratio, 0.25)
            * pullback_penalty
        )

        confidence = float(
            min(max(abs(aggregate_score), 0.0), 1.0)
            * max(agreement_ratio, 0.25)
            * (1.0 if regime_active else 0.4)
            * pullback_penalty
        )

        volatility_scalar = self.target_volatility / max(realized_vol, 1e-6)
        directional_scalar = min(max(regime_strength, 0.0) * max(timing_strength, 0.0), 1.0)
        raw_target = direction * min(
            volatility_scalar * directional_scalar * max(agreement_ratio, 0.25) * pullback_penalty,
            self.max_gross_leverage,
        )
        target_position = float(np.clip(raw_target, -self.max_gross_leverage, self.max_gross_leverage))
        if self.long_only and target_position < 0:
            target_position = 0.0

        horizon_forecasts: list[HorizonForecast] = []
        horizon_weights = {horizon: weight for horizon, weight in horizons}
        for horizon_bars, score, metadata in horizon_features:
            horizon_expected_return = float(
                realized_vol
                * np.sqrt(horizon_bars / max(self.periods_per_year, 1))
                * float(np.tanh(score / 2.0))
            )
            horizon_forecasts.append(
                HorizonForecast(
                    horizon_bars=horizon_bars,
                    expected_return=horizon_expected_return,
                    signal_strength=score,
                    weight=horizon_weights[horizon_bars],
                    metadata=metadata,
                )
            )

        latest_return = float(returns[-1])
        self.asset_returns.append(latest_return)
        self.strategy_returns.append(latest_return * self.current_target_position)
        self.current_target_position = target_position

        regime_label = self._regime_label(
            regime_strength=regime_strength,
            timing_strength=timing_strength,
            agreement_ratio=agreement_ratio,
            target_position=target_position,
        )
        rationale = (
            f"regime_strength={regime_strength:.4f}, "
            f"timing_strength={timing_strength:.4f}, "
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
                "regime_strength": regime_strength,
                "timing_strength": timing_strength,
                "regime_active": float(regime_active),
                "timing_active": float(timing_active),
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
                "regime_strength": regime_strength,
                "timing_strength": timing_strength,
                "regime_active": float(regime_active),
                "timing_active": float(timing_active),
                "pullback_penalty": pullback_penalty,
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
    def _horizon_features(returns: np.ndarray, horizon_bars: int) -> tuple[float, dict[str, float]]:
        horizon_window = returns[-horizon_bars:]
        horizon_mean = float(np.mean(horizon_window))
        horizon_std = float(np.std(horizon_window, ddof=1))
        cumulative_return = float(np.sum(horizon_window))
        standardized_return = cumulative_return / max(horizon_std * np.sqrt(horizon_bars), 1e-8)
        recent_return = float(np.sum(horizon_window[-max(3, horizon_bars // 5) :]))
        acceleration = recent_return - cumulative_return / max(horizon_bars, 1)
        return standardized_return, {
            "mean_return": horizon_mean,
            "cumulative_return": cumulative_return,
            "direction": float(np.sign(standardized_return)),
            "standardized_return": standardized_return,
            "recent_return": recent_return,
            "acceleration": acceleration,
        }

    @staticmethod
    def _regime_label(
        regime_strength: float,
        timing_strength: float,
        agreement_ratio: float,
        target_position: float,
    ) -> str:
        if target_position <= 0:
            return "flat_or_untrusted"
        if regime_strength > 0.5 and timing_strength > 0.35 and agreement_ratio >= 0.99:
            return "aligned_uptrend"
        if regime_strength > 0.35 and timing_strength > 0.15 and agreement_ratio >= 0.5:
            return "partially_aligned_uptrend"
        return "weak_uptrend"
