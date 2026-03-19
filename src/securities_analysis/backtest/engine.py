from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from securities_analysis.agents.contracts import Bar
from securities_analysis.backtest.costs import ExecutionCostModel
from securities_analysis.risk.metrics import RiskReport
from securities_analysis.risk.metrics import build_risk_report
from securities_analysis.risk.policy import RiskPolicy
from securities_analysis.strategies.trend_following import TimeSeriesMomentumStrategy


@dataclass(slots=True)
class BacktestStep:
    bar: Bar
    approved: bool
    reason: str
    target_position: float
    desired_quantity: float
    equity: float
    session_return: float
    spread_bps: float = 0.0
    turnover_fraction: float = 0.0
    gross_return: float = 0.0
    cost_return: float = 0.0
    net_return: float = 0.0


@dataclass(slots=True)
class BacktestResult:
    symbol: str
    bars_processed: int
    warmup_bars: int
    trades: int
    final_equity: float
    cumulative_return: float
    risk_report: RiskReport
    steps: list[BacktestStep] = field(default_factory=list)


@dataclass(slots=True)
class StrategyBacktester:
    strategy: TimeSeriesMomentumStrategy
    risk_policy: RiskPolicy
    initial_equity: float = 100_000.0
    spread_bps: float = 0.0
    time_in_force: str = "day"
    cost_model: ExecutionCostModel = field(default_factory=ExecutionCostModel)

    def run(self, bars: list[Bar]) -> BacktestResult:
        equity = self.initial_equity
        session_start_equity = self.initial_equity
        current_quantity = 0.0
        trades = 0
        steps: list[BacktestStep] = []
        warmup_bars = 0
        net_returns: list[float] = []

        for bar in bars:
            signal = self.strategy.on_bar(bar)
            if signal is None:
                warmup_bars += 1
                continue

            session_return = equity / max(session_start_equity, 1e-8) - 1.0
            decision = self.risk_policy.evaluate(
                signal=signal,
                equity=equity,
                price=bar.close_price,
                spread_bps=self.spread_bps,
                session_return=session_return,
                historical_strategy_returns=self.strategy.get_strategy_returns(),
            )

            turnover_fraction = 0.0
            if decision.flatten_position:
                turnover_fraction = abs(current_quantity) * bar.close_price / max(equity, 1e-8)
                if abs(current_quantity) > 1e-8:
                    trades += 1
                current_quantity = 0.0
            elif decision.approved:
                desired_signed_quantity = decision.desired_quantity * (
                    1.0 if signal.target_position >= 0 else -1.0
                )
                turnover_fraction = (
                    abs(desired_signed_quantity - current_quantity) * bar.close_price / max(equity, 1e-8)
                )
                if abs(desired_signed_quantity - current_quantity) > 1e-8:
                    trades += 1
                current_quantity = desired_signed_quantity

            gross_return = self._latest_strategy_return()
            cost_return = self.cost_model.estimate_cost_return(
                turnover_fraction=turnover_fraction,
                spread_bps=self.spread_bps,
            )
            net_return = gross_return - cost_return
            net_returns.append(net_return)
            equity *= 1.0 + net_return
            steps.append(
                BacktestStep(
                    bar=bar,
                    approved=decision.approved,
                    reason=decision.reason,
                    target_position=signal.target_position,
                    desired_quantity=current_quantity,
                    equity=equity,
                    session_return=session_return,
                    spread_bps=self.spread_bps,
                    turnover_fraction=turnover_fraction,
                    gross_return=gross_return,
                    cost_return=cost_return,
                    net_return=net_return,
                )
            )

        final_report = build_risk_report(
            np.array(net_returns, dtype=float),
            self.risk_policy.periods_per_year,
        )

        return BacktestResult(
            symbol=self.strategy.symbol,
            bars_processed=len(bars),
            warmup_bars=warmup_bars,
            trades=trades,
            final_equity=equity,
            cumulative_return=equity / self.initial_equity - 1.0,
            risk_report=final_report,
            steps=steps,
        )

    def warmup(self, bars: list[Bar]) -> int:
        warmed = 0
        for bar in bars:
            self.strategy.on_bar(bar)
            warmed += 1
        return warmed

    def _latest_strategy_return(self) -> float:
        returns = self.strategy.get_strategy_returns()
        if returns.size == 0:
            return 0.0
        return float(returns[-1])
