from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from securities_analysis.agents.contracts import OrderIntent, OrderType, SignalDecision, Side
from securities_analysis.risk.metrics import RiskReport, build_risk_report


@dataclass(slots=True)
class RiskDecision:
    approved: bool
    reason: str
    desired_notional: float = 0.0
    desired_quantity: float = 0.0
    flatten_position: bool = False
    report: RiskReport | None = None
    metadata: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class RiskPolicy:
    periods_per_year: int
    max_gross_leverage: float = 1.0
    max_position_notional_pct: float = 0.20
    max_trade_notional_pct: float = 0.10
    max_daily_drawdown_pct: float = 0.03
    max_spread_bps: float = 20.0
    min_order_notional: float = 50.0
    fractional_kelly: float = 0.25
    max_kelly_fraction: float = 0.50
    allow_short: bool = False
    min_history_for_kelly: int = 20

    def evaluate(
        self,
        signal: SignalDecision,
        equity: float,
        price: float,
        spread_bps: float | None,
        session_return: float,
        historical_strategy_returns: np.ndarray,
    ) -> RiskDecision:
        report = build_risk_report(historical_strategy_returns, self.periods_per_year)

        if session_return <= -abs(self.max_daily_drawdown_pct):
            return RiskDecision(
                approved=False,
                reason="Daily drawdown limit breached",
                flatten_position=True,
                report=report,
            )

        if spread_bps is not None and spread_bps > self.max_spread_bps:
            return RiskDecision(
                approved=False,
                reason=f"Spread too wide ({spread_bps:.2f} bps)",
                report=report,
            )

        target_fraction = self._target_fraction(
            signal=signal,
            report=report,
            historical_strategy_returns=historical_strategy_returns,
        )
        if target_fraction <= 0:
            return RiskDecision(
                approved=False,
                reason="Risk-adjusted target exposure is zero",
                flatten_position=True,
                report=report,
            )

        desired_notional = equity * target_fraction
        desired_notional = min(desired_notional, equity * self.max_trade_notional_pct)
        desired_quantity = desired_notional / max(price, 1e-8)
        if desired_notional < self.min_order_notional:
            return RiskDecision(
                approved=False,
                reason="Order notional below minimum threshold",
                report=report,
            )

        return RiskDecision(
            approved=True,
            reason="Approved",
            desired_notional=desired_notional,
            desired_quantity=desired_quantity,
            report=report,
            metadata={
                "target_fraction": target_fraction,
                "kelly_fraction": self._kelly_fraction(historical_strategy_returns),
                "spread_bps": spread_bps or 0.0,
            },
        )

    def build_order_intent(
        self,
        signal: SignalDecision,
        desired_quantity_delta: float,
        time_in_force: str,
    ) -> OrderIntent | None:
        if abs(desired_quantity_delta) <= 0:
            return None

        side = Side.BUY if desired_quantity_delta > 0 else Side.SELL
        if not self.allow_short and signal.target_position < 0:
            return None

        return OrderIntent(
            symbol=signal.symbol,
            created_at=signal.decision_time,
            side=side,
            order_type=OrderType.MARKET,
            quantity=abs(desired_quantity_delta),
            time_in_force=time_in_force,
            strategy_id=signal.signal_name,
            metadata=signal.metadata,
        )

    def _target_fraction(
        self,
        signal: SignalDecision,
        report: RiskReport,
        historical_strategy_returns: np.ndarray,
    ) -> float:
        signal_fraction = min(abs(signal.target_position), self.max_position_notional_pct)
        kelly_fraction = self._kelly_fraction(historical_strategy_returns)
        if signal.target_position < 0 and not self.allow_short:
            return 0.0
        return min(signal_fraction * kelly_fraction, self.max_position_notional_pct)

    def _kelly_fraction(self, returns: np.ndarray) -> float:
        clean_returns = np.asarray(returns, dtype=float)
        clean_returns = clean_returns[np.isfinite(clean_returns)]
        if clean_returns.size < self.min_history_for_kelly:
            return min(self.fractional_kelly, self.max_kelly_fraction)

        mean_return = float(np.mean(clean_returns))
        variance = float(np.var(clean_returns, ddof=1)) if clean_returns.size > 1 else 0.0
        raw_kelly = mean_return / max(variance, 1e-8)
        clipped = float(np.clip(raw_kelly, 0.0, self.max_kelly_fraction))
        return float(min(clipped * self.fractional_kelly, self.max_kelly_fraction))
