from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class RiskReport:
    observations: int
    annual_return: float
    annual_volatility: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    value_at_risk_95: float
    expected_shortfall_95: float
    hit_rate: float
    profit_factor: float
    stability: float


def build_risk_report(returns: np.ndarray, periods_per_year: int) -> RiskReport:
    clean_returns = np.asarray(returns, dtype=float)
    clean_returns = clean_returns[np.isfinite(clean_returns)]
    if clean_returns.size == 0:
        return RiskReport(
            observations=0,
            annual_return=0.0,
            annual_volatility=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            calmar_ratio=0.0,
            value_at_risk_95=0.0,
            expected_shortfall_95=0.0,
            hit_rate=0.0,
            profit_factor=0.0,
            stability=0.0,
        )

    mean_return = float(np.mean(clean_returns))
    volatility = float(np.std(clean_returns, ddof=1)) if clean_returns.size > 1 else 0.0
    annual_return = mean_return * periods_per_year
    annual_volatility = volatility * np.sqrt(periods_per_year)
    sharpe_ratio = annual_return / max(annual_volatility, 1e-8)

    downside = clean_returns[clean_returns < 0]
    downside_vol = float(np.std(downside, ddof=1)) if downside.size > 1 else 0.0
    annual_downside_vol = downside_vol * np.sqrt(periods_per_year)
    sortino_ratio = annual_return / max(annual_downside_vol, 1e-8)

    equity_curve = np.cumprod(1.0 + clean_returns)
    running_max = np.maximum.accumulate(equity_curve)
    drawdowns = equity_curve / np.maximum(running_max, 1e-8) - 1.0
    max_drawdown = float(np.min(drawdowns))
    calmar_ratio = annual_return / max(abs(max_drawdown), 1e-8)

    value_at_risk_95 = float(np.quantile(clean_returns, 0.05))
    expected_shortfall_95 = float(np.mean(clean_returns[clean_returns <= value_at_risk_95]))

    wins = clean_returns[clean_returns > 0]
    losses = clean_returns[clean_returns < 0]
    hit_rate = float(wins.size / clean_returns.size)
    profit_factor = float(np.sum(wins) / max(abs(np.sum(losses)), 1e-8))

    time_index = np.arange(clean_returns.size, dtype=float)
    stability = _compute_stability(time_index, np.log(np.maximum(equity_curve, 1e-8)))

    return RiskReport(
        observations=int(clean_returns.size),
        annual_return=annual_return,
        annual_volatility=annual_volatility,
        sharpe_ratio=sharpe_ratio,
        sortino_ratio=sortino_ratio,
        max_drawdown=max_drawdown,
        calmar_ratio=calmar_ratio,
        value_at_risk_95=value_at_risk_95,
        expected_shortfall_95=expected_shortfall_95,
        hit_rate=hit_rate,
        profit_factor=profit_factor,
        stability=stability,
    )


def _compute_stability(x_values: np.ndarray, y_values: np.ndarray) -> float:
    if x_values.size < 3:
        return 0.0
    x_mean = float(np.mean(x_values))
    y_mean = float(np.mean(y_values))
    covariance = float(np.sum((x_values - x_mean) * (y_values - y_mean)))
    variance_x = float(np.sum((x_values - x_mean) ** 2))
    if variance_x <= 0:
        return 0.0
    slope = covariance / variance_x
    intercept = y_mean - slope * x_mean
    fitted = slope * x_values + intercept
    residual_sum = float(np.sum((y_values - fitted) ** 2))
    total_sum = float(np.sum((y_values - y_mean) ** 2))
    if total_sum <= 0:
        return 0.0
    return float(max(0.0, 1.0 - residual_sum / total_sum))

