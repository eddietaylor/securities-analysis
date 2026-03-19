from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExecutionCostModel:
    """Simple but more realistic cost model for backtests."""

    commission_bps: float = 0.0
    slippage_bps: float = 2.0
    market_impact_bps_per_turnover: float = 5.0

    def estimate_cost_return(
        self,
        turnover_fraction: float,
        spread_bps: float,
    ) -> float:
        if turnover_fraction <= 0:
            return 0.0

        half_spread_bps = max(spread_bps, 0.0) / 2.0
        impact_bps = self.market_impact_bps_per_turnover * turnover_fraction
        total_bps = self.commission_bps + self.slippage_bps + half_spread_bps + impact_bps
        return turnover_fraction * total_bps / 10000.0

