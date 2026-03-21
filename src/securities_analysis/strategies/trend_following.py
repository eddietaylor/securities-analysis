from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from securities_analysis.agents.contracts import ForecastSnapshot, HorizonForecast, Bar, SignalDecision


@dataclass(slots=True)
class TimeSeriesMomentumStrategy:
    """Public-evidence MVP: time-series momentum with vol scaling."""

    symbol: str
    lookback_bars: int = 30
    vol_lookback_bars: int = 20
    target_volatility: float = 0.20
    max_gross_leverage: float = 1.0
    periods_per_year: int = 252 * 6.5 * 60
    min_bars: int = 35
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

        momentum_window = returns[-self.lookback_bars :]
        vol_window = returns[-self.vol_lookback_bars :]
        realized_vol = float(np.std(vol_window, ddof=1) * np.sqrt(self.periods_per_year))
        momentum_score = float(np.sum(momentum_window))
        normalized_momentum = momentum_score / max(np.std(momentum_window, ddof=1), 1e-8)

        direction = 1.0 if normalized_momentum > 0 else -1.0
        if self.long_only and direction < 0:
            direction = 0.0

        volatility_scalar = self.target_volatility / max(realized_vol, 1e-6)
        raw_target = direction * min(volatility_scalar, self.max_gross_leverage)
        target_position = float(np.clip(raw_target, -self.max_gross_leverage, self.max_gross_leverage))
        confidence = float(min(abs(normalized_momentum) / 5.0, 1.0))

        latest_return = float(returns[-1])
        self.asset_returns.append(latest_return)
        self.strategy_returns.append(latest_return * self.current_target_position)
        self.current_target_position = target_position

        rationale = (
            f"momentum={momentum_score:.6f}, "
            f"normalized_momentum={normalized_momentum:.4f}, "
            f"realized_vol={realized_vol:.4f}, "
            f"target_position={target_position:.4f}"
        )
        self.latest_forecast = ForecastSnapshot(
            symbol=self.symbol,
            forecast_time=bar.end_time,
            model_name="time_series_momentum",
            aggregate_expected_return=momentum_score,
            aggregate_score=normalized_momentum,
            realized_volatility=realized_vol,
            confidence=confidence,
            regime_label="uptrend" if target_position > 0 else "flat_or_downtrend",
            horizons=[
                HorizonForecast(
                    horizon_bars=self.lookback_bars,
                    expected_return=momentum_score,
                    signal_strength=normalized_momentum,
                    weight=1.0,
                    metadata={"direction": direction},
                )
            ],
            metadata={
                "target_position": target_position,
                "close_price": bar.close_price,
            },
        )
        return SignalDecision(
            symbol=self.symbol,
            decision_time=bar.end_time,
            signal_name="time_series_momentum",
            target_position=target_position,
            confidence=confidence,
            rationale=rationale,
            metadata={
                "momentum_score": momentum_score,
                "normalized_momentum": normalized_momentum,
                "realized_volatility": realized_vol,
                "close_price": bar.close_price,
            },
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

