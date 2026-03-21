from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

from securities_analysis.backtest.engine import BacktestResult
from securities_analysis.dashboard import build_backtest_dashboard, build_forecast_dashboard
from securities_analysis.forecast_validation import compute_forecast_diagnostics


def save_backtest_artifacts(
    result: BacktestResult,
    output_dir: str | Path,
    metadata: dict[str, Any] | None = None,
) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    summary_path = artifact_dir / "summary.json"
    steps_path = artifact_dir / "steps.csv"
    chart_path = artifact_dir / "equity_drawdown.png"
    forecast_metrics_path = artifact_dir / "forecast_horizon_metrics.csv"
    forecast_summary_path = artifact_dir / "forecast_diagnostics_summary.json"

    summary_payload = {
        "symbol": result.symbol,
        "bars_processed": result.bars_processed,
        "warmup_bars": result.warmup_bars,
        "trades": result.trades,
        "final_equity": result.final_equity,
        "cumulative_return": result.cumulative_return,
        "risk_report": asdict(result.risk_report),
    }
    if metadata:
        summary_payload["metadata"] = metadata
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    steps_frame = pd.DataFrame(
        [
            _step_to_record(step)
            for step in result.steps
        ]
    )
    steps_frame.to_csv(steps_path, index=False)

    if not steps_frame.empty:
        forecast_metrics_frame, forecast_summary = compute_forecast_diagnostics(steps_frame)
        forecast_metrics_frame.to_csv(forecast_metrics_path, index=False)
        forecast_summary_path.write_text(json.dumps(forecast_summary, indent=2), encoding="utf-8")
        _save_equity_drawdown_chart(steps_frame, chart_path, result.symbol)
        build_backtest_dashboard(artifact_dir)
        build_forecast_dashboard(artifact_dir)

    return artifact_dir


def _step_to_record(step) -> dict[str, Any]:
    payload = {
        "timestamp": step.bar.end_time.isoformat(),
        "symbol": step.bar.symbol,
        "close_price": step.bar.close_price,
        "signal_name": step.signal_name,
        "signal_confidence": step.signal_confidence,
        "signal_rationale": step.signal_rationale,
        "approved": step.approved,
        "reason": step.reason,
        "target_position": step.target_position,
        "desired_quantity": step.desired_quantity,
        "equity": step.equity,
        "session_return": step.session_return,
        "spread_bps": step.spread_bps,
        "turnover_fraction": step.turnover_fraction,
        "gross_return": step.gross_return,
        "cost_return": step.cost_return,
        "net_return": step.net_return,
    }
    for key, value in step.signal_metadata.items():
        if isinstance(value, (int, float, str, bool)) or value is None:
            payload[key] = value
    return payload


def _save_equity_drawdown_chart(
    steps_frame: pd.DataFrame,
    chart_path: Path,
    symbol: str,
) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return

    steps_frame = steps_frame.copy()
    steps_frame["timestamp"] = pd.to_datetime(steps_frame["timestamp"])
    steps_frame["running_max"] = steps_frame["equity"].cummax()
    steps_frame["drawdown"] = steps_frame["equity"] / steps_frame["running_max"] - 1.0

    figure, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

    axes[0].plot(steps_frame["timestamp"], steps_frame["equity"], label="Equity", color="#0b84a5")
    axes[0].set_title(f"{symbol} Backtest Equity Curve")
    axes[0].set_ylabel("Equity")
    axes[0].grid(True, alpha=0.3)

    axes[1].fill_between(
        steps_frame["timestamp"],
        steps_frame["drawdown"],
        0.0,
        color="#d1495b",
        alpha=0.35,
    )
    axes[1].set_ylabel("Drawdown")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(
        steps_frame["timestamp"],
        steps_frame["target_position"],
        label="Target Position",
        color="#4c956c",
    )
    axes[2].set_ylabel("Target")
    axes[2].set_xlabel("Time")
    axes[2].grid(True, alpha=0.3)

    figure.tight_layout()
    figure.savefig(chart_path, dpi=150, bbox_inches="tight")
    plt.close(figure)
