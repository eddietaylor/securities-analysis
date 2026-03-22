from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from securities_analysis.agents.contracts import Bar, ForecastSnapshot, HorizonForecast, SignalDecision


@dataclass(slots=True)
class _OnlineRidgeModel:
    feature_names: list[str]
    alpha: float = 1.0
    min_train_samples: int = 60
    max_train_samples: int | None = None
    x_rows: list[np.ndarray] = field(default_factory=list)
    y_rows: list[float] = field(default_factory=list)

    def add_sample(self, features: np.ndarray, target: float) -> None:
        self.x_rows.append(features.astype(float))
        self.y_rows.append(float(target))
        if self.max_train_samples is not None:
            while len(self.y_rows) > self.max_train_samples:
                self.x_rows.pop(0)
                self.y_rows.pop(0)

    def ready(self) -> bool:
        return len(self.y_rows) >= max(self.min_train_samples, len(self.feature_names) + 5)

    def predict(self, features: np.ndarray) -> tuple[float, float, dict[str, float]]:
        if not self.ready():
            return 0.0, 0.0, {
                "train_samples": float(len(self.y_rows)),
                "target_mean": 0.0,
                "target_std": 0.0,
                "prediction_raw": 0.0,
            }

        x = np.vstack(self.x_rows)
        y = np.asarray(self.y_rows, dtype=float)

        x_mean = x.mean(axis=0)
        x_std = x.std(axis=0, ddof=1)
        x_std = np.where(x_std < 1e-8, 1.0, x_std)
        x_scaled = (x - x_mean) / x_std

        y_mean = float(y.mean())
        y_centered = y - y_mean
        gram = x_scaled.T @ x_scaled + self.alpha * np.eye(x_scaled.shape[1])
        coeffs = np.linalg.solve(gram, x_scaled.T @ y_centered)

        features_scaled = (features - x_mean) / x_std
        prediction = float(y_mean + features_scaled @ coeffs)
        target_std = float(np.std(y, ddof=1)) if y.size > 1 else 0.0
        signal_strength = prediction / max(target_std, 1e-8) if target_std > 0 else 0.0

        feature_contributions = coeffs * features_scaled
        metadata = {
            "train_samples": float(len(self.y_rows)),
            "target_mean": y_mean,
            "target_std": target_std,
            "prediction_raw": prediction,
        }
        metadata.update(
            {
                f"coef_contrib_{name}": float(value)
                for name, value in zip(self.feature_names, feature_contributions, strict=True)
            }
        )
        return prediction, float(signal_strength), metadata


@dataclass(slots=True)
class FeatureLinearForecastStrategy:
    """Feature-based expanding-window ridge forecaster over multiple horizons."""

    symbol: str
    lookback_bars: int = 60
    vol_lookback_bars: int = 20
    target_volatility: float = 0.15
    max_gross_leverage: float = 1.0
    periods_per_year: int = 252
    min_bars: int = 90
    long_only: bool = True
    ridge_alpha: float = 2.0
    min_train_samples: int = 80
    max_train_samples: int | None = None
    bars: deque[Bar] = field(default_factory=deque)
    asset_returns: deque[float] = field(default_factory=deque)
    strategy_returns: deque[float] = field(default_factory=deque)
    current_target_position: float = 0.0
    latest_forecast: ForecastSnapshot | None = None
    pending_samples: dict[int, deque[tuple[np.ndarray, float]]] = field(default_factory=dict)
    models: dict[int, _OnlineRidgeModel] = field(default_factory=dict)
    feature_names: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.feature_names = [
            "ret_5",
            "ret_10",
            "ret_20",
            "ret_long",
            "vol_short",
            "vol_long",
            "vol_ratio",
            "ma_spread_short_long",
            "ma_spread_medium_long",
            "drawdown_from_peak",
            "breakout_distance",
        ]
        for horizon in self._horizons():
            horizon_min_train = max(30, min(self.min_train_samples, max(horizon // 2, len(self.feature_names) + 8)))
            self.pending_samples[horizon] = deque()
            self.models[horizon] = _OnlineRidgeModel(
                feature_names=self.feature_names,
                alpha=self.ridge_alpha,
                min_train_samples=horizon_min_train,
                max_train_samples=self.max_train_samples,
            )

    def on_bar(self, bar: Bar) -> SignalDecision | None:
        self._append_bar(bar)
        closes = np.array([item.close_price for item in self.bars], dtype=float)
        if len(closes) < self.min_bars:
            return None

        current_price = float(closes[-1])
        features = self._build_features(closes)
        if features is None:
            return None

        for horizon in self._horizons():
            if len(self.pending_samples[horizon]) >= horizon:
                matured_features, anchor_price = self.pending_samples[horizon].popleft()
                realized_target = float(np.log(current_price / max(anchor_price, 1e-8)))
                self.models[horizon].add_sample(matured_features, realized_target)

        returns = np.diff(np.log(closes))
        realized_vol = float(np.std(returns[-self.vol_lookback_bars :], ddof=1) * np.sqrt(self.periods_per_year))

        horizon_forecasts: list[HorizonForecast] = []
        horizon_predictions: dict[int, float] = {}
        horizon_scores: dict[int, float] = {}

        for horizon in self._horizons():
            prediction, signal_strength, metadata = self.models[horizon].predict(features)
            horizon_predictions[horizon] = prediction
            horizon_scores[horizon] = signal_strength
            horizon_forecasts.append(
                HorizonForecast(
                    horizon_bars=horizon,
                    expected_return=prediction,
                    signal_strength=signal_strength,
                    weight=self._horizon_weight(horizon),
                    metadata=metadata,
                )
            )

        short_horizon, medium_horizon, long_horizon = self._horizons()
        regime_score = horizon_scores[long_horizon]
        if not self.models[long_horizon].ready():
            regime_score = float(0.6 * horizon_scores[medium_horizon] + 0.4 * horizon_scores[short_horizon])
        timing_score = float(0.65 * horizon_scores[short_horizon] + 0.35 * horizon_scores[medium_horizon])
        aggregate_score = float(0.6 * regime_score + 0.4 * timing_score)
        aggregate_expected_return = float(
            0.2 * horizon_predictions[short_horizon]
            + 0.3 * horizon_predictions[medium_horizon]
            + 0.5 * horizon_predictions[long_horizon]
        )
        agreement_ratio = float(
            np.mean(
                [
                    1.0 if np.sign(horizon_scores[h]) == np.sign(regime_score) and np.sign(horizon_scores[h]) != 0 else 0.0
                    for h in (short_horizon, medium_horizon)
                ]
            )
        ) if np.sign(regime_score) != 0 else 0.0

        regime_active = regime_score > 0.05
        timing_active = timing_score > 0.02
        direction = 1.0 if (regime_active and timing_active) else 0.0
        if not self.long_only and aggregate_score < 0:
            direction = -1.0 if timing_score < -0.02 and regime_score < -0.05 else 0.0
        if self.long_only and direction < 0:
            direction = 0.0

        confidence = float(
            min(abs(aggregate_score), 1.0)
            * max(agreement_ratio, 0.25)
            * min(len(self.models[long_horizon].y_rows) / max(self.models[long_horizon].min_train_samples, 1), 1.0)
        )
        volatility_scalar = self.target_volatility / max(realized_vol, 1e-6)
        directional_scalar = min(max(aggregate_score, 0.0), 1.0) if direction > 0 else min(abs(aggregate_score), 1.0)
        raw_target = direction * min(
            volatility_scalar * directional_scalar * max(agreement_ratio, 0.25),
            self.max_gross_leverage,
        )
        target_position = float(np.clip(raw_target, -self.max_gross_leverage, self.max_gross_leverage))
        if self.long_only and target_position < 0:
            target_position = 0.0

        latest_return = float(returns[-1])
        self.asset_returns.append(latest_return)
        self.strategy_returns.append(latest_return * self.current_target_position)
        self.current_target_position = target_position

        regime_label = self._regime_label(regime_score, timing_score, target_position)
        rationale = (
            f"regime_score={regime_score:.4f}, "
            f"timing_score={timing_score:.4f}, "
            f"agreement_ratio={agreement_ratio:.3f}, "
            f"realized_vol={realized_vol:.4f}, "
            f"target_position={target_position:.4f}"
        )
        self.latest_forecast = ForecastSnapshot(
            symbol=self.symbol,
            forecast_time=bar.end_time,
            model_name="feature_linear_forecast",
            aggregate_expected_return=aggregate_expected_return,
            aggregate_score=aggregate_score,
            realized_volatility=realized_vol,
            confidence=confidence,
            regime_label=regime_label,
            horizons=horizon_forecasts,
            metadata={
                "agreement_ratio": agreement_ratio,
                "regime_score": regime_score,
                "timing_score": timing_score,
                "regime_active": float(regime_active),
                "timing_active": float(timing_active),
                "target_position": target_position,
                "close_price": bar.close_price,
            },
        )

        metadata = {
            f"h{forecast.horizon_bars}_expected_return": forecast.expected_return
            for forecast in horizon_forecasts
        }
        metadata.update(
            {
                f"h{forecast.horizon_bars}_signal_strength": forecast.signal_strength
                for forecast in horizon_forecasts
            }
        )
        for forecast in horizon_forecasts:
            for key, value in forecast.metadata.items():
                metadata[f"h{forecast.horizon_bars}_{key}"] = value
        metadata.update(
            {
                "aggregate_expected_return": aggregate_expected_return,
                "aggregate_score": aggregate_score,
                "agreement_ratio": agreement_ratio,
                "regime_score": regime_score,
                "timing_score": timing_score,
                "regime_active": float(regime_active),
                "timing_active": float(timing_active),
                "realized_volatility": realized_vol,
                "close_price": bar.close_price,
                "regime_label": regime_label,
            }
        )

        for horizon in self._horizons():
            self.pending_samples[horizon].append((features.copy(), current_price))

        return SignalDecision(
            symbol=self.symbol,
            decision_time=bar.end_time,
            signal_name="feature_linear_forecast",
            target_position=target_position,
            confidence=confidence,
            rationale=rationale,
            metadata=metadata,
        )

    def get_strategy_returns(self) -> np.ndarray:
        return np.array(self.strategy_returns, dtype=float)

    def get_asset_returns(self) -> np.ndarray:
        return np.array(self.asset_returns, dtype=float)

    def get_latest_forecast(self) -> ForecastSnapshot | None:
        return self.latest_forecast

    def _append_bar(self, bar: Bar) -> None:
        max_bars = max(self.min_bars, self.lookback_bars, self.vol_lookback_bars) + max(self._horizons()) + 5
        self.bars.append(bar)
        while len(self.bars) > max_bars:
            self.bars.popleft()

    def _build_features(self, closes: np.ndarray) -> np.ndarray | None:
        returns = np.diff(np.log(closes))
        if len(returns) < max(self.lookback_bars, self.vol_lookback_bars, 20):
            return None

        def cumulative_log_return(window: int) -> float:
            return float(np.sum(returns[-window:]))

        def annualized_vol(window: int) -> float:
            return float(np.std(returns[-window:], ddof=1) * np.sqrt(self.periods_per_year))

        short_window = max(5, self.lookback_bars // 4)
        medium_window = max(10, self.lookback_bars // 2)
        long_window = self.lookback_bars
        vol_short_window = max(5, self.vol_lookback_bars)
        vol_long_window = max(vol_short_window + 5, self.lookback_bars)

        ma_short = float(np.mean(closes[-short_window:]))
        ma_medium = float(np.mean(closes[-medium_window:]))
        ma_long = float(np.mean(closes[-long_window:]))
        rolling_peak = float(np.max(closes[-long_window:]))
        rolling_high = float(np.max(closes[-short_window:]))

        vol_short = annualized_vol(vol_short_window)
        vol_long = annualized_vol(min(vol_long_window, len(returns)))

        feature_values = np.array(
            [
                cumulative_log_return(short_window),
                cumulative_log_return(min(10, len(returns))),
                cumulative_log_return(min(20, len(returns))),
                cumulative_log_return(long_window),
                vol_short,
                vol_long,
                vol_short / max(vol_long, 1e-8),
                (closes[-1] / max(ma_short, 1e-8)) - (closes[-1] / max(ma_long, 1e-8)),
                (closes[-1] / max(ma_medium, 1e-8)) - (closes[-1] / max(ma_long, 1e-8)),
                np.log(closes[-1] / max(rolling_peak, 1e-8)),
                np.log(closes[-1] / max(rolling_high, 1e-8)),
            ],
            dtype=float,
        )
        return feature_values

    def _horizons(self) -> tuple[int, int, int]:
        short_horizon = max(5, self.lookback_bars // 4)
        medium_horizon = max(short_horizon + 1, self.lookback_bars // 2)
        return short_horizon, medium_horizon, self.lookback_bars

    def _horizon_weight(self, horizon: int) -> float:
        short_horizon, medium_horizon, long_horizon = self._horizons()
        if horizon == short_horizon:
            return 0.2
        if horizon == medium_horizon:
            return 0.3
        if horizon == long_horizon:
            return 0.5
        return 1.0 / 3.0

    @staticmethod
    def _regime_label(regime_score: float, timing_score: float, target_position: float) -> str:
        if target_position <= 0:
            return "flat_or_untrusted"
        if regime_score > 0.25 and timing_score > 0.10:
            return "aligned_feature_uptrend"
        if regime_score > 0.10 and timing_score > 0.02:
            return "partial_feature_uptrend"
        return "weak_feature_uptrend"
