from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from securities_analysis.agents.contracts import Bar, ForecastSnapshot, HorizonForecast, SignalDecision
from securities_analysis.strategies.forecast_features import (
    build_forecast_feature_vector,
    forecast_feature_names,
)


@dataclass(slots=True)
class _OnlineBoostedModel:
    feature_names: list[str]
    min_train_samples: int = 80
    max_train_samples: int | None = None
    learning_rate: float = 0.05
    n_estimators: int = 40
    max_depth: int = 2
    random_state: int = 7
    refit_every: int = 10
    x_rows: list[np.ndarray] = field(default_factory=list)
    y_rows: list[float] = field(default_factory=list)
    fitted_model: GradientBoostingRegressor | None = None
    samples_since_fit: int = 0
    last_feature_importances: np.ndarray | None = None

    def add_sample(self, features: np.ndarray, target: float) -> None:
        self.x_rows.append(features.astype(float))
        self.y_rows.append(float(target))
        if self.max_train_samples is not None:
            while len(self.y_rows) > self.max_train_samples:
                self.x_rows.pop(0)
                self.y_rows.pop(0)
        self.samples_since_fit += 1

    def ready(self) -> bool:
        return len(self.y_rows) >= max(self.min_train_samples, len(self.feature_names) + 12)

    def predict(self, features: np.ndarray) -> tuple[float, float, dict[str, float]]:
        if not self.ready():
            return 0.0, 0.0, {
                "train_samples": float(len(self.y_rows)),
                "target_mean": 0.0,
                "target_std": 0.0,
                "prediction_raw": 0.0,
            }

        if self.fitted_model is None or self.samples_since_fit >= self.refit_every:
            x = np.vstack(self.x_rows)
            y = np.asarray(self.y_rows, dtype=float)
            model = GradientBoostingRegressor(
                learning_rate=self.learning_rate,
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                random_state=self.random_state,
                loss="squared_error",
            )
            model.fit(x, y)
            self.fitted_model = model
            self.last_feature_importances = np.asarray(model.feature_importances_, dtype=float)
            self.samples_since_fit = 0

        y = np.asarray(self.y_rows, dtype=float)
        prediction = float(self.fitted_model.predict(features.reshape(1, -1))[0])
        target_std = float(np.std(y, ddof=1)) if y.size > 1 else 0.0
        signal_strength = prediction / max(target_std, 1e-8) if target_std > 0 else 0.0
        metadata = {
            "train_samples": float(len(self.y_rows)),
            "target_mean": float(np.mean(y)),
            "target_std": target_std,
            "prediction_raw": prediction,
        }
        metadata.update(
            {
                f"feature_importance_{name}": float(value)
                for name, value in zip(
                    self.feature_names,
                    self.last_feature_importances if self.last_feature_importances is not None else np.zeros(len(self.feature_names)),
                    strict=True,
                )
            }
        )
        return prediction, float(signal_strength), metadata


@dataclass(slots=True)
class FeatureBoostedForecastStrategy:
    symbol: str
    lookback_bars: int = 60
    vol_lookback_bars: int = 20
    target_volatility: float = 0.15
    max_gross_leverage: float = 1.0
    periods_per_year: int = 252
    min_bars: int = 120
    long_only: bool = True
    min_train_samples: int = 100
    max_train_samples: int | None = None
    selection_window: int = 80
    bars: deque[Bar] = field(default_factory=deque)
    asset_returns: deque[float] = field(default_factory=deque)
    strategy_returns: deque[float] = field(default_factory=deque)
    current_target_position: float = 0.0
    latest_forecast: ForecastSnapshot | None = None
    feature_names: list[str] = field(default_factory=forecast_feature_names)
    pending_samples: dict[int, deque[tuple[np.ndarray, float, float]]] = field(default_factory=dict)
    models: dict[int, _OnlineBoostedModel] = field(default_factory=dict)
    horizon_eval_history: dict[int, deque[tuple[float, float]]] = field(default_factory=lambda: defaultdict(deque))

    def __post_init__(self) -> None:
        for horizon in self._candidate_horizons():
            self.pending_samples[horizon] = deque()
            self.models[horizon] = _OnlineBoostedModel(
                feature_names=self.feature_names,
                min_train_samples=max(40, min(self.min_train_samples, max(horizon, len(self.feature_names) + 15))),
                max_train_samples=self.max_train_samples,
            )

    def on_bar(self, bar: Bar) -> SignalDecision | None:
        self._append_bar(bar)
        closes = np.array([item.close_price for item in self.bars], dtype=float)
        if len(closes) < self.min_bars:
            return None

        current_price = float(closes[-1])
        features = build_forecast_feature_vector(
            closes,
            periods_per_year=self.periods_per_year,
            lookback_bars=self.lookback_bars,
            vol_lookback_bars=self.vol_lookback_bars,
            timestamp=bar.end_time,
        )
        if features is None:
            return None

        returns = np.diff(np.log(closes))
        realized_vol = float(np.std(returns[-self.vol_lookback_bars :], ddof=1) * np.sqrt(self.periods_per_year))

        for horizon in self._candidate_horizons():
            if len(self.pending_samples[horizon]) >= horizon:
                matured_features, anchor_price, prior_prediction = self.pending_samples[horizon].popleft()
                realized_target = float(np.log(current_price / max(anchor_price, 1e-8)))
                self.models[horizon].add_sample(matured_features, realized_target)
                history = self.horizon_eval_history[horizon]
                history.append((prior_prediction, realized_target))
                while len(history) > self.selection_window:
                    history.popleft()

        horizon_forecasts: list[HorizonForecast] = []
        horizon_predictions: dict[int, float] = {}
        horizon_scores: dict[int, float] = {}
        horizon_metadata: dict[int, dict[str, float]] = {}
        horizon_quality: dict[int, float] = {}

        for horizon in self._candidate_horizons():
            prediction, signal_strength, metadata = self.models[horizon].predict(features)
            quality = self._horizon_quality_score(horizon)
            horizon_predictions[horizon] = prediction
            horizon_scores[horizon] = signal_strength
            horizon_metadata[horizon] = metadata
            horizon_quality[horizon] = quality
            horizon_forecasts.append(
                HorizonForecast(
                    horizon_bars=horizon,
                    expected_return=prediction,
                    signal_strength=signal_strength,
                    weight=quality,
                    metadata={
                        **metadata,
                        "quality_score": quality,
                    },
                )
            )

        selected_short, selected_medium, selected_long = self._select_active_horizons()
        short_score = horizon_scores[selected_short]
        medium_score = horizon_scores[selected_medium]
        long_score = horizon_scores[selected_long]
        short_prediction = horizon_predictions[selected_short]
        medium_prediction = horizon_predictions[selected_medium]
        long_prediction = horizon_predictions[selected_long]
        regime_score = float(0.7 * np.tanh(long_score / 2.0) + 0.3 * np.tanh(medium_score / 2.0))
        timing_score = float(0.55 * np.tanh(short_score / 2.0) + 0.45 * np.tanh(medium_score / 2.0))
        aggregate_score = float(0.6 * regime_score + 0.4 * timing_score)
        aggregate_expected_return = float(0.25 * short_prediction + 0.35 * medium_prediction + 0.40 * long_prediction)
        agreement_ratio = float(
            np.mean(
                [
                    1.0 if np.sign(value) == np.sign(regime_score) and np.sign(value) != 0 else 0.0
                    for value in (short_score, medium_score, long_score)
                ]
            )
        ) if np.sign(regime_score) != 0 else 0.0

        regime_active = regime_score > 0.04
        timing_active = timing_score > 0.02
        direction = 1.0 if (regime_active and timing_active) else 0.0
        if not self.long_only and regime_score < -0.04 and timing_score < -0.02:
            direction = -1.0
        if self.long_only and direction < 0:
            direction = 0.0

        selection_confidence = float(np.mean([max(horizon_quality[h], 0.0) for h in (selected_short, selected_medium, selected_long)]))
        confidence = float(min(abs(aggregate_score), 1.0) * max(agreement_ratio, 0.25) * min(selection_confidence + 0.25, 1.0))
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
            f"selected_horizons=({selected_short},{selected_medium},{selected_long}), "
            f"regime_score={regime_score:.4f}, timing_score={timing_score:.4f}, "
            f"agreement_ratio={agreement_ratio:.3f}, realized_vol={realized_vol:.4f}, "
            f"target_position={target_position:.4f}"
        )

        self.latest_forecast = ForecastSnapshot(
            symbol=self.symbol,
            forecast_time=bar.end_time,
            model_name="feature_boosted_forecast",
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
                "selected_short_horizon": float(selected_short),
                "selected_medium_horizon": float(selected_medium),
                "selected_long_horizon": float(selected_long),
                "selection_confidence": selection_confidence,
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
                "selection_confidence": selection_confidence,
                "selected_short_horizon": float(selected_short),
                "selected_medium_horizon": float(selected_medium),
                "selected_long_horizon": float(selected_long),
                "realized_volatility": realized_vol,
                "close_price": bar.close_price,
                "regime_label": regime_label,
            }
        )

        for horizon in self._candidate_horizons():
            self.pending_samples[horizon].append((features.copy(), current_price, horizon_predictions[horizon]))

        return SignalDecision(
            symbol=self.symbol,
            decision_time=bar.end_time,
            signal_name="feature_boosted_forecast",
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
        max_bars = max(self.min_bars, self.lookback_bars, self.vol_lookback_bars) + max(self._candidate_horizons()) + 5
        self.bars.append(bar)
        while len(self.bars) > max_bars:
            self.bars.popleft()

    def _candidate_horizons(self) -> tuple[int, ...]:
        raw = [5, 10, 15, 20, max(25, self.lookback_bars // 2), self.lookback_bars]
        return tuple(sorted({int(value) for value in raw if value > 1}))

    def _select_active_horizons(self) -> tuple[int, int, int]:
        candidates = self._candidate_horizons()
        short_bucket = [h for h in candidates if h <= 15]
        medium_bucket = [h for h in candidates if 15 < h < self.lookback_bars]
        long_bucket = [h for h in candidates if h >= self.lookback_bars]
        if not medium_bucket:
            medium_bucket = [max(candidates[:-1])]
        if not long_bucket:
            long_bucket = [candidates[-1]]
        return (
            self._select_from_bucket(short_bucket),
            self._select_from_bucket(medium_bucket),
            self._select_from_bucket(long_bucket),
        )

    def _select_from_bucket(self, bucket: list[int]) -> int:
        scored = [(self._horizon_quality_score(horizon), horizon) for horizon in bucket]
        scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
        return scored[0][1]

    def _horizon_quality_score(self, horizon: int) -> float:
        history = self.horizon_eval_history[horizon]
        if len(history) < max(20, horizon // 2):
            return 0.0
        predictions = np.array([item[0] for item in history], dtype=float)
        realized = np.array([item[1] for item in history], dtype=float)
        if predictions.size < 2 or np.std(predictions) < 1e-10 or np.std(realized) < 1e-10:
            return 0.0
        correlation = float(np.corrcoef(predictions, realized)[0, 1])
        hit_rate = float(np.mean(np.sign(predictions) == np.sign(realized)))
        return 0.7 * correlation + 0.3 * (hit_rate - 0.5)

    @staticmethod
    def _regime_label(regime_score: float, timing_score: float, target_position: float) -> str:
        if target_position <= 0:
            return "flat_or_untrusted"
        if regime_score > 0.20 and timing_score > 0.08:
            return "boosted_aligned_uptrend"
        if regime_score > 0.08 and timing_score > 0.02:
            return "boosted_partial_uptrend"
        return "boosted_weak_uptrend"
