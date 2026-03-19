from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from securities_analysis.agents.contracts import Bar, SignalDecision


@dataclass(slots=True)
class MeanReversionStrategy:
    """Simple public baseline: z-score mean reversion with vol scaling."""

    symbol: str
    lookback_bars: int = 20
    vol_lookback_bars: int = 10
    target_volatility: float = 0.10
    max_gross_leverage: float = 1.0
    periods_per_year: int = 252 * 6.5 * 60
    min_bars: int = 25
    long_only: bool = True
    entry_zscore: float = 1.0
    exit_zscore: float = 0.25
    bars: deque[Bar] = field(default_factory=deque)
    asset_returns: deque[float] = field(default_factory=deque)
    strategy_returns: deque[float] = field(default_factory=deque)
    current_target_position: float = 0.0

    def on_bar(self, bar: Bar) -> SignalDecision | None:
        self._append_bar(bar)
        if len(self.bars) < self.min_bars:
            return None

        closes = np.array([item.close_price for item in self.bars], dtype=float)
        returns = np.diff(np.log(closes))
        if len(returns) < max(self.lookback_bars, self.vol_lookback_bars):
            return None

        price_window = closes[-self.lookback_bars :]
        vol_window = returns[-self.vol_lookback_bars :]
        realized_vol = float(np.std(vol_window, ddof=1) * np.sqrt(self.periods_per_year))
        window_mean = float(np.mean(price_window))
        window_std = float(np.std(price_window, ddof=1))
        zscore = (bar.close_price - window_mean) / max(window_std, 1e-8)

        direction = 0.0
        if zscore <= -abs(self.entry_zscore):
            direction = 1.0
        elif not self.long_only and zscore >= abs(self.entry_zscore):
            direction = -1.0
        elif abs(zscore) <= abs(self.exit_zscore):
            direction = 0.0
        else:
            direction = self.current_target_position

        volatility_scalar = self.target_volatility / max(realized_vol, 1e-6)
        raw_target = direction * min(volatility_scalar, self.max_gross_leverage)
        target_position = float(np.clip(raw_target, -self.max_gross_leverage, self.max_gross_leverage))
        if self.long_only and target_position < 0:
            target_position = 0.0

        latest_return = float(returns[-1])
        self.asset_returns.append(latest_return)
        self.strategy_returns.append(latest_return * self.current_target_position)
        self.current_target_position = target_position

        confidence = float(min(abs(zscore) / max(abs(self.entry_zscore), 1e-8), 1.0))
        rationale = (
            f"zscore={zscore:.4f}, "
            f"window_mean={window_mean:.4f}, "
            f"window_std={window_std:.4f}, "
            f"realized_vol={realized_vol:.4f}, "
            f"target_position={target_position:.4f}"
        )
        return SignalDecision(
            symbol=self.symbol,
            decision_time=bar.end_time,
            signal_name="mean_reversion_zscore",
            target_position=target_position,
            confidence=confidence,
            rationale=rationale,
            metadata={
                "zscore": zscore,
                "window_mean": window_mean,
                "window_std": window_std,
                "realized_volatility": realized_vol,
                "close_price": bar.close_price,
            },
        )

    def get_strategy_returns(self) -> np.ndarray:
        return np.array(self.strategy_returns, dtype=float)

    def get_asset_returns(self) -> np.ndarray:
        return np.array(self.asset_returns, dtype=float)

    def _append_bar(self, bar: Bar) -> None:
        max_bars = max(self.min_bars, self.lookback_bars, self.vol_lookback_bars) + 5
        self.bars.append(bar)
        while len(self.bars) > max_bars:
            self.bars.popleft()
