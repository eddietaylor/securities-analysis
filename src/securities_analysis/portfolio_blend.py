from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from securities_analysis.risk.metrics import RiskReport, build_risk_report


@dataclass(slots=True)
class PortfolioBlendResult:
    weights_frame: pd.DataFrame
    summary: dict[str, Any]


def evaluate_portfolio_blends(
    steps_frame: pd.DataFrame,
    *,
    periods_per_year: int = 252,
    sleeve_weights: list[float] | None = None,
) -> PortfolioBlendResult:
    working = steps_frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    if "net_return" not in working.columns:
        raise KeyError("steps frame missing required column: net_return")
    if "market_buy_hold_cumulative_return" not in working.columns:
        raise KeyError("steps frame missing required column: market_buy_hold_cumulative_return")

    working["sleeve_return"] = pd.to_numeric(working["net_return"], errors="coerce").fillna(0.0)
    market_cumulative = pd.to_numeric(working["market_buy_hold_cumulative_return"], errors="coerce").fillna(method="ffill").fillna(0.0)
    working["market_return"] = (1.0 + market_cumulative).pct_change(fill_method=None).fillna(0.0)

    weights = sleeve_weights or [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    rows: list[dict[str, float]] = []

    sleeve_report = build_risk_report(working["sleeve_return"].to_numpy(dtype=float), periods_per_year)
    market_report = build_risk_report(working["market_return"].to_numpy(dtype=float), periods_per_year)
    sleeve_vs_market_corr = _safe_corr(
        working["sleeve_return"].to_numpy(dtype=float),
        working["market_return"].to_numpy(dtype=float),
    )

    for sleeve_weight in weights:
        market_weight = 1.0 - sleeve_weight
        blended_returns = sleeve_weight * working["sleeve_return"] + market_weight * working["market_return"]
        report = build_risk_report(blended_returns.to_numpy(dtype=float), periods_per_year)
        cumulative_return = float(np.prod(1.0 + blended_returns.to_numpy(dtype=float)) - 1.0)
        rows.append(
            {
                "sleeve_weight": float(sleeve_weight),
                "market_weight": float(market_weight),
                "cumulative_return": cumulative_return,
                "annual_return": report.annual_return,
                "annual_volatility": report.annual_volatility,
                "sharpe_ratio": report.sharpe_ratio,
                "sortino_ratio": report.sortino_ratio,
                "max_drawdown": report.max_drawdown,
                "calmar_ratio": report.calmar_ratio,
                "stability": report.stability,
            }
        )

    weights_frame = pd.DataFrame(rows).sort_values("sleeve_weight").reset_index(drop=True)
    summary = {
        "periods_per_year": periods_per_year,
        "sleeve_report": _risk_report_to_dict(sleeve_report),
        "market_report": _risk_report_to_dict(market_report),
        "sleeve_vs_market_correlation": sleeve_vs_market_corr,
        "best_sharpe_weight": _best_row(weights_frame, "sharpe_ratio"),
        "best_calmar_weight": _best_row(weights_frame, "calmar_ratio"),
        "lowest_drawdown_weight": _best_row(weights_frame, "max_drawdown", ascending=False),
    }
    return PortfolioBlendResult(weights_frame=weights_frame, summary=summary)


def save_portfolio_blend_artifacts(
    result: PortfolioBlendResult,
    *,
    output_dir: str | Path,
) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result.weights_frame.to_csv(artifact_dir / "blend_metrics.csv", index=False)
    (artifact_dir / "summary.json").write_text(json.dumps(result.summary, indent=2), encoding="utf-8")
    return artifact_dir


def default_portfolio_blend_output_dir() -> Path:
    stamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "portfolio_blends" / f"blend_{stamp}"


def load_backtest_steps_frame(artifact_dir: str | Path) -> pd.DataFrame:
    return pd.read_csv(Path(artifact_dir) / "steps.csv")


def _safe_corr(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 2 or y.size < 2:
        return float("nan")
    if np.std(x) <= 0 or np.std(y) <= 0:
        return float("nan")
    return float(np.corrcoef(x, y)[0, 1])


def _risk_report_to_dict(report: RiskReport) -> dict[str, float | int]:
    return {
        "observations": report.observations,
        "annual_return": report.annual_return,
        "annual_volatility": report.annual_volatility,
        "sharpe_ratio": report.sharpe_ratio,
        "sortino_ratio": report.sortino_ratio,
        "max_drawdown": report.max_drawdown,
        "calmar_ratio": report.calmar_ratio,
        "value_at_risk_95": report.value_at_risk_95,
        "expected_shortfall_95": report.expected_shortfall_95,
        "hit_rate": report.hit_rate,
        "profit_factor": report.profit_factor,
        "stability": report.stability,
    }


def _best_row(frame: pd.DataFrame, metric: str, *, ascending: bool = False) -> dict[str, float]:
    if frame.empty or metric not in frame.columns:
        return {}
    ordered = frame.sort_values(metric, ascending=ascending)
    row = ordered.iloc[0]
    return {
        "sleeve_weight": float(row["sleeve_weight"]),
        "market_weight": float(row["market_weight"]),
        metric: float(row[metric]),
        "cumulative_return": float(row["cumulative_return"]),
    }
