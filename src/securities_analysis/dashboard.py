from __future__ import annotations

import json
import math
from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd

from securities_analysis.forecast_validation import add_realized_horizon_returns, compute_forecast_diagnostics


def build_backtest_dashboard(
    artifact_dir: str | Path,
    *,
    output_path: str | Path | None = None,
) -> Path:
    artifact_path = Path(artifact_dir)
    summary = json.loads((artifact_path / "summary.json").read_text(encoding="utf-8"))
    steps_frame = pd.read_csv(artifact_path / "steps.csv")
    if steps_frame.empty:
        raise ValueError(f"No backtest steps found in {artifact_path}")

    initial_equity = _infer_initial_equity(summary)
    steps_frame = _prepare_steps_frame(steps_frame, initial_equity=initial_equity)
    output = Path(output_path) if output_path else artifact_path / "dashboard.html"

    chart_paths = _generate_dashboard_charts(artifact_path, steps_frame, summary["symbol"])
    html = _render_backtest_dashboard_html(
        artifact_path=artifact_path,
        summary=summary,
        steps_frame=steps_frame,
        chart_paths=chart_paths,
    )
    output.write_text(html, encoding="utf-8")
    return output


def build_forecast_dashboard(
    artifact_dir: str | Path,
    *,
    output_path: str | Path | None = None,
) -> Path:
    artifact_path = Path(artifact_dir)
    summary = json.loads((artifact_path / "summary.json").read_text(encoding="utf-8"))
    steps_frame = pd.read_csv(artifact_path / "steps.csv")
    if steps_frame.empty:
        raise ValueError(f"No backtest steps found in {artifact_path}")

    diagnostics_frame, diagnostics_summary = compute_forecast_diagnostics(steps_frame)
    output = Path(output_path) if output_path else artifact_path / "forecast_dashboard.html"
    chart_paths = _generate_forecast_charts(artifact_path, steps_frame, diagnostics_frame)
    html = _render_forecast_dashboard_html(
        artifact_path=artifact_path,
        summary=summary,
        steps_frame=steps_frame,
        diagnostics_frame=diagnostics_frame,
        diagnostics_summary=diagnostics_summary,
        chart_paths=chart_paths,
    )
    output.write_text(html, encoding="utf-8")
    return output


def build_registry_dashboard_index(
    *,
    registry_path: str | Path = Path("artifacts") / "registry" / "run_registry.jsonl",
    output_path: str | Path = Path("artifacts") / "dashboard" / "index.html",
    kinds: set[str] | None = None,
) -> Path:
    registry = _load_registry(registry_path)
    if kinds:
        registry = [entry for entry in registry if entry.get("kind") in kinds]

    rows: list[dict[str, Any]] = []
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    for entry in registry:
        artifact_dir = Path(entry["artifact_dir"])
        dashboard_path = artifact_dir / "dashboard.html"
        forecast_dashboard_path = artifact_dir / "forecast_dashboard.html"
        if entry.get("kind") == "backtest" and artifact_dir.exists():
            try:
                build_backtest_dashboard(artifact_dir)
            except Exception:
                pass
            try:
                build_forecast_dashboard(artifact_dir)
            except Exception:
                pass

        relative_dashboard = ""
        if dashboard_path.exists():
            relative_dashboard = str(Path("..") / artifact_dir.relative_to("artifacts") / "dashboard.html").replace("\\", "/")
        relative_forecast_dashboard = ""
        if forecast_dashboard_path.exists():
            relative_forecast_dashboard = str(Path("..") / artifact_dir.relative_to("artifacts") / "forecast_dashboard.html").replace("\\", "/")

        config = entry.get("config", {})
        runtime_spec = config.get("runtime_spec", {})
        strategy = runtime_spec.get("strategy", {})
        risk = runtime_spec.get("risk", {})
        summary = entry.get("summary", {})

        rows.append(
            {
                "run_id": entry.get("run_id", ""),
                "kind": entry.get("kind", ""),
                "created_at": entry.get("created_at", ""),
                "symbol": config.get("symbol", ""),
                "asset_class": config.get("asset_class", ""),
                "start": config.get("start", ""),
                "end": config.get("end", ""),
                "strategy_family": strategy.get("family", ""),
                "lookback_bars": strategy.get("lookback_bars", ""),
                "target_volatility": strategy.get("target_volatility", ""),
                "fractional_kelly": risk.get("fractional_kelly", ""),
                "cumulative_return": summary.get("cumulative_return", ""),
                "sharpe_ratio": summary.get("sharpe_ratio", ""),
                "max_drawdown": summary.get("max_drawdown", ""),
                "dashboard_href": relative_dashboard,
                "forecast_dashboard_href": relative_forecast_dashboard,
            }
        )

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("created_at", ascending=False)

    html = _render_index_html(frame)
    output.write_text(html, encoding="utf-8")
    return output


def _prepare_steps_frame(steps_frame: pd.DataFrame, *, initial_equity: float) -> pd.DataFrame:
    frame = steps_frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["running_max"] = frame["equity"].cummax()
    frame["drawdown"] = frame["equity"] / frame["running_max"] - 1.0
    frame["rolling_vol_20"] = frame["net_return"].rolling(20).std(ddof=1) * math.sqrt(252)
    frame["rolling_turnover_20"] = frame["turnover_fraction"].rolling(20).mean()
    frame["cumulative_gross_return"] = (1.0 + frame["gross_return"]).cumprod() - 1.0
    frame["cumulative_net_return"] = (1.0 + frame["net_return"]).cumprod() - 1.0
    frame["cumulative_cost_drag"] = frame["cost_return"].cumsum()
    first_close = float(frame["close_price"].iloc[0])
    frame["buy_hold_equity"] = initial_equity * (frame["close_price"] / max(first_close, 1e-8))
    frame["buy_hold_running_max"] = frame["buy_hold_equity"].cummax()
    frame["buy_hold_drawdown"] = frame["buy_hold_equity"] / frame["buy_hold_running_max"] - 1.0
    frame["buy_hold_cumulative_return"] = frame["buy_hold_equity"] / max(initial_equity, 1e-8) - 1.0
    return frame


def _generate_dashboard_charts(
    artifact_path: Path,
    steps_frame: pd.DataFrame,
    symbol: str,
) -> dict[str, str]:
    chart_dir = artifact_path / "dashboard_assets"
    chart_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return {}

    generated: dict[str, str] = {}

    figure, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
    axes[0].plot(steps_frame["timestamp"], steps_frame["equity"], color="#0b84a5", label="Strategy")
    if "buy_hold_equity" in steps_frame.columns:
        axes[0].plot(steps_frame["timestamp"], steps_frame["buy_hold_equity"], color="#7f7f7f", linestyle="--", label="Buy & Hold")
    axes[0].set_title(f"{symbol} Equity Curve vs Buy & Hold")
    axes[0].set_ylabel("Equity")
    axes[0].legend()
    axes[0].grid(True, alpha=0.25)

    axes[1].fill_between(steps_frame["timestamp"], steps_frame["drawdown"], 0.0, color="#d1495b", alpha=0.35, label="Strategy")
    if "buy_hold_drawdown" in steps_frame.columns:
        axes[1].plot(steps_frame["timestamp"], steps_frame["buy_hold_drawdown"], color="#7f7f7f", linestyle="--", label="Buy & Hold")
    axes[1].set_title("Drawdown vs Buy & Hold")
    axes[1].set_ylabel("Drawdown")
    axes[1].legend()
    axes[1].grid(True, alpha=0.25)

    axes[2].plot(steps_frame["timestamp"], steps_frame["target_position"], color="#4c956c")
    axes[2].set_title("Target Position")
    axes[2].set_ylabel("Target")
    axes[2].set_xlabel("Time")
    axes[2].grid(True, alpha=0.25)

    path = chart_dir / "equity_drawdown_target.png"
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    generated["equity"] = path.name

    figure, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    axes[0].plot(steps_frame["timestamp"], steps_frame["rolling_vol_20"], color="#6c5ce7")
    axes[0].set_title("Rolling 20-Period Annualized Volatility")
    axes[0].set_ylabel("Volatility")
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(steps_frame["timestamp"], steps_frame["rolling_turnover_20"], color="#ff7f11")
    axes[1].set_title("Rolling 20-Period Average Turnover")
    axes[1].set_ylabel("Turnover")
    axes[1].set_xlabel("Time")
    axes[1].grid(True, alpha=0.25)

    path = chart_dir / "risk_activity.png"
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    generated["risk_activity"] = path.name

    figure, axes = plt.subplots(2, 1, figsize=(12, 7))
    axes[0].plot(steps_frame["timestamp"], steps_frame["cumulative_gross_return"], label="Gross", color="#0b84a5")
    axes[0].plot(steps_frame["timestamp"], steps_frame["cumulative_net_return"], label="Net", color="#4c956c")
    if "buy_hold_cumulative_return" in steps_frame.columns:
        axes[0].plot(steps_frame["timestamp"], steps_frame["buy_hold_cumulative_return"], label="Buy & Hold", color="#7f7f7f", linestyle="--")
    axes[0].set_title("Gross / Net / Buy & Hold Cumulative Return")
    axes[0].legend()
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(steps_frame["timestamp"], steps_frame["cumulative_cost_drag"], color="#d1495b")
    axes[1].set_title("Cumulative Cost Drag")
    axes[1].set_ylabel("Cost Return")
    axes[1].set_xlabel("Time")
    axes[1].grid(True, alpha=0.25)

    path = chart_dir / "returns_costs.png"
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    generated["returns_costs"] = path.name

    figure, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(steps_frame["net_return"], bins=30, color="#0b84a5", alpha=0.85)
    axes[0].set_title("Net Return Distribution")
    axes[0].grid(True, alpha=0.2)

    trade_frame = steps_frame.loc[steps_frame["turnover_fraction"] > 0]
    axes[1].hist(trade_frame["turnover_fraction"], bins=30, color="#ff7f11", alpha=0.85)
    axes[1].set_title("Trade Turnover Distribution")
    axes[1].grid(True, alpha=0.2)

    path = chart_dir / "distributions.png"
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    generated["distributions"] = path.name

    return generated


def _render_backtest_dashboard_html(
    *,
    artifact_path: Path,
    summary: dict[str, Any],
    steps_frame: pd.DataFrame,
    chart_paths: dict[str, str],
) -> str:
    risk_report = summary.get("risk_report", {})
    metadata = summary.get("metadata", {})
    runtime_spec = metadata.get("runtime_spec", {})
    strategy_spec = runtime_spec.get("strategy", {})
    risk_spec = runtime_spec.get("risk", {})
    costs = metadata.get("costs", {})
    buy_hold_return = float(steps_frame["buy_hold_cumulative_return"].iloc[-1]) if "buy_hold_cumulative_return" in steps_frame.columns else None
    strategy_return = summary.get("cumulative_return")
    excess_vs_buy_hold = None
    if buy_hold_return is not None and strategy_return is not None:
        excess_vs_buy_hold = float(strategy_return) - float(buy_hold_return)

    trade_frame = steps_frame.loc[steps_frame["turnover_fraction"] > 0, [
        "timestamp",
        "close_price",
        "target_position",
        "desired_quantity",
        "turnover_fraction",
        "gross_return",
        "cost_return",
        "net_return",
        "reason",
    ]].tail(50)
    reject_frame = steps_frame.loc[~steps_frame["approved"], [
        "timestamp",
        "reason",
        "target_position",
        "desired_quantity",
        "turnover_fraction",
    ]].tail(50)

    cards = [
        ("Final Equity", _fmt_money(summary.get("final_equity"))),
        ("Cumulative Return", _fmt_pct(summary.get("cumulative_return"))),
        ("Buy & Hold Return", _fmt_pct(buy_hold_return)),
        ("Excess vs Buy & Hold", _fmt_pct(excess_vs_buy_hold)),
        ("Sharpe Ratio", _fmt_float(risk_report.get("sharpe_ratio"))),
        ("Max Drawdown", _fmt_pct(risk_report.get("max_drawdown"))),
        ("Trades", str(summary.get("trades", ""))),
        ("Warmup Bars", str(summary.get("warmup_bars", ""))),
    ]

    strategy_table = _dict_to_table_rows(strategy_spec)
    risk_table = _dict_to_table_rows(risk_spec)
    cost_table = _dict_to_table_rows(costs)
    risk_metrics_table = _dict_to_table_rows(risk_report)
    forecast_dashboard_exists = (artifact_path / "forecast_dashboard.html").exists()

    chart_html = "".join(
        f"<section class='panel'><h2>{escape(title)}</h2><img src='dashboard_assets/{escape(path)}' alt='{escape(title)} chart'></section>"
        for title, path in [
            ("Equity, Drawdown, and Positioning", chart_paths.get("equity", "")),
            ("Volatility and Trading Activity", chart_paths.get("risk_activity", "")),
            ("Returns and Cost Drag", chart_paths.get("returns_costs", "")),
            ("Distributions", chart_paths.get("distributions", "")),
        ]
        if path
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Backtest Dashboard | {escape(summary.get("symbol", ""))}</title>
  <style>
    body {{ font-family: "Segoe UI", sans-serif; margin: 0; background: #f6f8fb; color: #18212b; }}
    header {{ padding: 24px 32px; background: linear-gradient(135deg, #0b84a5, #4c956c); color: white; }}
    main {{ padding: 24px 32px 40px; max-width: 1400px; margin: 0 auto; }}
    .meta {{ opacity: 0.92; margin-top: 6px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 20px 0 28px; }}
    .card {{ background: white; border-radius: 14px; padding: 16px 18px; box-shadow: 0 8px 28px rgba(14, 28, 45, 0.08); }}
    .card h3 {{ margin: 0 0 8px; font-size: 0.95rem; color: #536273; }}
    .card .value {{ font-size: 1.45rem; font-weight: 700; }}
    .two-col {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-bottom: 24px; }}
    .panel {{ background: white; border-radius: 14px; padding: 18px; box-shadow: 0 8px 28px rgba(14, 28, 45, 0.08); margin-bottom: 24px; }}
    .panel h2 {{ margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #e6ebf2; text-align: left; vertical-align: top; }}
    th {{ color: #536273; font-weight: 600; }}
    img {{ max-width: 100%; border-radius: 10px; }}
    .mono {{ font-family: Consolas, monospace; }}
  </style>
</head>
<body>
  <header>
    <h1>Backtest Dashboard: {escape(summary.get("symbol", ""))}</h1>
    <div class="meta mono">{escape(str(artifact_path))}</div>
    <div class="meta">Run ID: <span class="mono">{escape(metadata.get("run_id", ""))}</span></div>
  </header>
  <main>
    <section class="panel">
      <h2>Related Views</h2>
      <p>
        {"<a href='forecast_dashboard.html'>Open Forecast Diagnostics Dashboard</a>" if forecast_dashboard_exists else "Forecast diagnostics dashboard not generated yet."}
      </p>
    </section>

    <section class="grid">
      {"".join(f"<div class='card'><h3>{escape(label)}</h3><div class='value'>{escape(value)}</div></div>" for label, value in cards)}
    </section>

    <section class="two-col">
      <div class="panel">
        <h2>Strategy Spec</h2>
        <table>{strategy_table}</table>
      </div>
      <div class="panel">
        <h2>Risk Spec</h2>
        <table>{risk_table}</table>
      </div>
    </section>

    <section class="two-col">
      <div class="panel">
        <h2>Cost Model</h2>
        <table>{cost_table}</table>
      </div>
      <div class="panel">
        <h2>Risk Metrics</h2>
        <table>{risk_metrics_table}</table>
      </div>
    </section>

    {chart_html}

    <section class="two-col">
      <div class="panel">
        <h2>Recent Trades</h2>
        {_frame_to_html(trade_frame, max_rows=20)}
      </div>
      <div class="panel">
        <h2>Recent Risk Rejections / Flatten Events</h2>
        {_frame_to_html(reject_frame, max_rows=20)}
      </div>
    </section>
  </main>
</body>
</html>
"""


def _generate_forecast_charts(
    artifact_path: Path,
    steps_frame: pd.DataFrame,
    diagnostics_frame: pd.DataFrame,
) -> dict[str, str]:
    chart_dir = artifact_path / "dashboard_assets"
    chart_dir.mkdir(parents=True, exist_ok=True)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        return {}

    generated: dict[str, str] = {}
    working = steps_frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"])

    if "aggregate_score" in working.columns or "signal_confidence" in working.columns:
        figure, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
        if "aggregate_score" in working.columns:
            axes[0].plot(working["timestamp"], working["aggregate_score"], color="#0b84a5")
            axes[0].axhline(0.0, color="black", linewidth=1, linestyle="--", alpha=0.5)
            axes[0].set_title("Aggregate Forecast Score")
            axes[0].set_ylabel("Score")
            axes[0].grid(True, alpha=0.25)
        if "signal_confidence" in working.columns:
            axes[1].plot(working["timestamp"], working["signal_confidence"], color="#4c956c")
            axes[1].set_title("Signal Confidence")
            axes[1].set_ylabel("Confidence")
            axes[1].set_xlabel("Time")
            axes[1].grid(True, alpha=0.25)
        path = chart_dir / "forecast_signal_confidence.png"
        figure.tight_layout()
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        generated["signal_confidence"] = path.name

    if not diagnostics_frame.empty:
        figure, axes = plt.subplots(1, 2, figsize=(12, 4))
        axes[0].bar(diagnostics_frame["horizon_bars"].astype(str), diagnostics_frame["correlation"], color="#0b84a5")
        axes[0].set_title("Forecast vs Realized Correlation")
        axes[0].set_xlabel("Horizon")
        axes[0].set_ylabel("Correlation")
        axes[0].grid(True, axis="y", alpha=0.25)

        axes[1].bar(
            diagnostics_frame["horizon_bars"].astype(str),
            diagnostics_frame["directional_accuracy"],
            color="#ff7f11",
        )
        axes[1].set_title("Directional Accuracy by Horizon")
        axes[1].set_xlabel("Horizon")
        axes[1].set_ylabel("Accuracy")
        axes[1].set_ylim(0, 1)
        axes[1].grid(True, axis="y", alpha=0.25)

        path = chart_dir / "forecast_metrics_by_horizon.png"
        figure.tight_layout()
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        generated["metrics_by_horizon"] = path.name

        first_row = diagnostics_frame.sort_values("horizon_bars").iloc[0]
        forecast_column = str(first_row["forecast_column"])
        realized_column = f"realized_return_h{int(first_row['horizon_bars'])}"
        frame = add_realized_horizon_returns(steps_frame.copy())
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame = frame[[forecast_column, realized_column]].dropna()
        if not frame.empty:
            figure, axes = plt.subplots(1, 2, figsize=(12, 4))
            axes[0].scatter(frame[forecast_column], frame[realized_column], alpha=0.6, color="#6c5ce7")
            axes[0].axhline(0.0, color="black", linewidth=1, linestyle="--", alpha=0.5)
            axes[0].axvline(0.0, color="black", linewidth=1, linestyle="--", alpha=0.5)
            axes[0].set_title(f"Forecast vs Realized (h={int(first_row['horizon_bars'])})")
            axes[0].set_xlabel("Forecast")
            axes[0].set_ylabel("Realized")
            axes[0].grid(True, alpha=0.25)

            axes[1].plot(frame.index, frame[forecast_column], label="Forecast", color="#0b84a5")
            axes[1].plot(frame.index, frame[realized_column], label="Realized", color="#d1495b")
            axes[1].set_title(f"Forecast and Realized Sequence (h={int(first_row['horizon_bars'])})")
            axes[1].legend()
            axes[1].grid(True, alpha=0.25)

            path = chart_dir / "forecast_vs_realized.png"
            figure.tight_layout()
            figure.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(figure)
            generated["forecast_vs_realized"] = path.name

    contribution_columns = [column for column in working.columns if "_coef_contrib_" in column]
    importance_columns = [column for column in working.columns if "feature_importance_" in column]
    diagnostic_columns = contribution_columns or importance_columns
    if diagnostic_columns:
        contribution_frame = working[diagnostic_columns].dropna(how="all")
        if not contribution_frame.empty:
            avg_abs = contribution_frame.abs().mean().sort_values(ascending=False).head(18)
            figure, ax = plt.subplots(figsize=(12, 6))
            ax.barh(avg_abs.index[::-1], avg_abs.values[::-1], color="#4c956c")
            chart_title = "Average Absolute Feature Contribution" if contribution_columns else "Average Feature Importance"
            axis_label = "Mean absolute contribution" if contribution_columns else "Mean importance"
            ax.set_title(chart_title)
            ax.set_xlabel(axis_label)
            ax.grid(True, axis="x", alpha=0.25)
            path = chart_dir / "feature_contributions_avg_abs.png"
            figure.tight_layout()
            figure.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(figure)
            generated["feature_contributions_avg_abs"] = path.name

            latest_idx = contribution_frame.index[-1]
            latest_contrib = contribution_frame.loc[latest_idx].dropna()
            if not latest_contrib.empty:
                latest_contrib = latest_contrib.reindex(latest_contrib.abs().sort_values(ascending=False).index).head(18)
                figure, ax = plt.subplots(figsize=(12, 6))
                colors = ["#0b84a5" if value >= 0 else "#d1495b" for value in latest_contrib.values[::-1]]
                ax.barh(latest_contrib.index[::-1], latest_contrib.values[::-1], color=colors)
                latest_title = "Latest Feature Contribution Snapshot" if contribution_columns else "Latest Feature Importance Snapshot"
                latest_axis_label = "Contribution" if contribution_columns else "Importance"
                ax.set_title(latest_title)
                ax.set_xlabel(latest_axis_label)
                ax.grid(True, axis="x", alpha=0.25)
                path = chart_dir / "feature_contributions_latest.png"
                figure.tight_layout()
                figure.savefig(path, dpi=150, bbox_inches="tight")
                plt.close(figure)
                generated["feature_contributions_latest"] = path.name

    return generated


def _render_forecast_dashboard_html(
    *,
    artifact_path: Path,
    summary: dict[str, Any],
    steps_frame: pd.DataFrame,
    diagnostics_frame: pd.DataFrame,
    diagnostics_summary: dict[str, Any],
    chart_paths: dict[str, str],
) -> str:
    metadata = summary.get("metadata", {})
    runtime_spec = metadata.get("runtime_spec", {})
    strategy_spec = runtime_spec.get("strategy", {})
    validation_method = diagnostics_summary.get("validation_method", {})
    forecastability = diagnostics_summary.get("forecastability", {})
    aggregate_signal = diagnostics_summary.get("aggregate_signal", {})
    recommended_horizons = diagnostics_summary.get("recommended_horizons", {})

    cards = [
        ("Model", str(strategy_spec.get("family", ""))),
        ("Bars Evaluated", str(len(steps_frame))),
        ("Horizon Metrics", str(len(diagnostics_frame))),
        ("Primary Signal", str(steps_frame["signal_name"].iloc[0]) if "signal_name" in steps_frame.columns and not steps_frame.empty else ""),
    ]

    validation_method_table = _dict_to_table_rows(validation_method)
    forecast_table = _dict_to_table_rows(forecastability)
    aggregate_table = _dict_to_table_rows(aggregate_signal)
    recommended_horizons_table = _dict_to_table_rows(recommended_horizons)
    diagnostics_table = _frame_to_html(diagnostics_frame, max_rows=10)
    feature_summary_table = _feature_summary_html(steps_frame)
    latest_feature_snapshot_table = _latest_feature_snapshot_html(steps_frame)

    chart_html = "".join(
        f"<section class='panel'><h2>{escape(title)}</h2><img src='dashboard_assets/{escape(path)}' alt='{escape(title)} chart'></section>"
        for title, path in [
            ("Forecast Score and Confidence", chart_paths.get("signal_confidence", "")),
            ("Horizon Metrics", chart_paths.get("metrics_by_horizon", "")),
            ("Forecast vs Realized", chart_paths.get("forecast_vs_realized", "")),
            ("Average Absolute Feature Contribution", chart_paths.get("feature_contributions_avg_abs", "")),
            ("Latest Feature Contribution Snapshot", chart_paths.get("feature_contributions_latest", "")),
        ]
        if path
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Forecast Diagnostics | {escape(summary.get("symbol", ""))}</title>
  <style>
    body {{ font-family: "Segoe UI", sans-serif; margin: 0; background: #f6f8fb; color: #18212b; }}
    header {{ padding: 24px 32px; background: linear-gradient(135deg, #18212b, #6c5ce7); color: white; }}
    main {{ padding: 24px 32px 40px; max-width: 1400px; margin: 0 auto; }}
    .meta {{ opacity: 0.92; margin-top: 6px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 20px 0 28px; }}
    .card {{ background: white; border-radius: 14px; padding: 16px 18px; box-shadow: 0 8px 28px rgba(14, 28, 45, 0.08); }}
    .card h3 {{ margin: 0 0 8px; font-size: 0.95rem; color: #536273; }}
    .card .value {{ font-size: 1.3rem; font-weight: 700; }}
    .two-col {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-bottom: 24px; }}
    .panel {{ background: white; border-radius: 14px; padding: 18px; box-shadow: 0 8px 28px rgba(14, 28, 45, 0.08); margin-bottom: 24px; }}
    .panel h2 {{ margin-top: 0; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.92rem; }}
    th, td {{ padding: 8px 10px; border-bottom: 1px solid #e6ebf2; text-align: left; vertical-align: top; }}
    th {{ color: #536273; font-weight: 600; }}
    img {{ max-width: 100%; border-radius: 10px; }}
    .mono {{ font-family: Consolas, monospace; }}
  </style>
</head>
<body>
  <header>
    <h1>Forecast Diagnostics: {escape(summary.get("symbol", ""))}</h1>
    <div class="meta mono">{escape(str(artifact_path))}</div>
    <div class="meta"><a href="dashboard.html" style="color: white;">Open Trading / Backtest Dashboard</a></div>
  </header>
  <main>
    <section class="grid">
      {"".join(f"<div class='card'><h3>{escape(label)}</h3><div class='value'>{escape(value)}</div></div>" for label, value in cards)}
    </section>

    <section class="two-col">
      <div class="panel">
        <h2>Validation Method</h2>
        <table>{validation_method_table}</table>
      </div>
      <div class="panel">
        <h2>Forecastability Diagnostics</h2>
        <table>{forecast_table}</table>
      </div>
      <div class="panel">
        <h2>Aggregate Signal Diagnostics</h2>
        <table>{aggregate_table}</table>
      </div>
      <div class="panel">
        <h2>Recommended Horizons</h2>
        <table>{recommended_horizons_table}</table>
      </div>
    </section>

    {chart_html}

    <section class="panel">
      <h2>Horizon Validation Metrics</h2>
      {diagnostics_table}
    </section>

    <section class="two-col">
      <div class="panel">
        <h2>Feature Contribution Summary</h2>
        {feature_summary_table}
      </div>
      <div class="panel">
        <h2>Latest Feature Snapshot</h2>
        {latest_feature_snapshot_table}
      </div>
    </section>
  </main>
</body>
</html>
"""


def _render_index_html(frame: pd.DataFrame) -> str:
    rows = []
    for _, row in frame.iterrows():
        dashboard_cell = (
            f"<a href='{escape(str(row['dashboard_href']))}'>open</a>"
            if row["dashboard_href"]
            else ""
        )
        forecast_dashboard_cell = (
            f"<a href='{escape(str(row['forecast_dashboard_href']))}'>open</a>"
            if row["forecast_dashboard_href"]
            else ""
        )
        rows.append(
            "<tr>"
            f"<td class='mono'>{escape(str(row['created_at']))}</td>"
            f"<td>{escape(str(row['kind']))}</td>"
            f"<td>{escape(str(row['symbol']))}</td>"
            f"<td>{escape(str(row['strategy_family']))}</td>"
            f"<td>{escape(str(row['start']))}</td>"
            f"<td>{escape(str(row['end']))}</td>"
            f"<td>{_fmt_pct(row['cumulative_return'])}</td>"
            f"<td>{_fmt_float(row['sharpe_ratio'])}</td>"
            f"<td>{_fmt_pct(row['max_drawdown'])}</td>"
            f"<td>{dashboard_cell}</td>"
            f"<td>{forecast_dashboard_cell}</td>"
            "</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Run Explorer</title>
  <style>
    body {{ font-family: "Segoe UI", sans-serif; margin: 0; background: #f6f8fb; color: #18212b; }}
    header {{ padding: 24px 32px; background: linear-gradient(135deg, #18212b, #0b84a5); color: white; }}
    main {{ padding: 24px 32px 40px; max-width: 1400px; margin: 0 auto; }}
    .panel {{ background: white; border-radius: 14px; padding: 18px; box-shadow: 0 8px 28px rgba(14, 28, 45, 0.08); }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.93rem; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #e6ebf2; text-align: left; }}
    th {{ color: #536273; font-weight: 600; }}
    .mono {{ font-family: Consolas, monospace; }}
  </style>
</head>
<body>
  <header>
    <h1>Run Explorer</h1>
    <div>Static index of tracked runs. Open one run to inspect its deep dashboard.</div>
  </header>
  <main>
    <section class="panel">
      <table>
        <thead>
          <tr>
            <th>Created</th>
            <th>Kind</th>
            <th>Symbol</th>
            <th>Strategy</th>
            <th>Start</th>
            <th>End</th>
            <th>Cumulative Return</th>
            <th>Sharpe</th>
            <th>Max Drawdown</th>
            <th>Trading</th>
            <th>Forecast</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def _dict_to_table_rows(payload: dict[str, Any]) -> str:
    return "".join(
        f"<tr><th>{escape(str(key))}</th><td>{escape(_fmt_generic(value))}</td></tr>"
        for key, value in payload.items()
    )


def _frame_to_html(frame: pd.DataFrame, *, max_rows: int = 20) -> str:
    if frame.empty:
        return "<p>No rows to display.</p>"
    trimmed = frame.tail(max_rows).copy()
    return trimmed.to_html(index=False, border=0, classes="dataframe")


def _feature_summary_html(frame: pd.DataFrame) -> str:
    contribution_columns = [column for column in frame.columns if "_coef_contrib_" in column]
    importance_columns = [column for column in frame.columns if "feature_importance_" in column]
    if not contribution_columns:
        if not importance_columns:
            return "<p>No feature contribution metadata found.</p>"
        importance_frame = frame[importance_columns].dropna(how="all")
        if importance_frame.empty:
            return "<p>Feature importance columns exist but no trained model rows are populated yet.</p>"
        summary = pd.DataFrame(
            {
                "feature_component": importance_frame.columns,
                "mean_importance": importance_frame.mean().values,
            }
        ).sort_values("mean_importance", ascending=False)
        return summary.head(20).to_html(index=False, border=0, classes="dataframe")
    contribution_frame = frame[contribution_columns].dropna(how="all")
    if contribution_frame.empty:
        return "<p>Feature contribution columns exist but no trained model rows are populated yet.</p>"

    summary = pd.DataFrame(
        {
            "feature_component": contribution_frame.columns,
            "mean_abs_contribution": contribution_frame.abs().mean().values,
            "mean_contribution": contribution_frame.mean().values,
        }
    ).sort_values("mean_abs_contribution", ascending=False)
    return summary.head(20).to_html(index=False, border=0, classes="dataframe")


def _latest_feature_snapshot_html(frame: pd.DataFrame) -> str:
    contribution_columns = [column for column in frame.columns if "_coef_contrib_" in column]
    importance_columns = [column for column in frame.columns if "feature_importance_" in column]
    snapshot_columns = [column for column in frame.columns if column.endswith("_prediction_raw") or column.endswith("_train_samples") or column.endswith("_target_std")]
    if not contribution_columns and not importance_columns and not snapshot_columns:
        return "<p>No model-state diagnostics found.</p>"

    model_state = frame[contribution_columns + importance_columns + snapshot_columns].dropna(how="all")
    if model_state.empty:
        return "<p>Model-state diagnostics are not populated yet.</p>"

    latest = model_state.iloc[-1].dropna()
    latest_frame = pd.DataFrame({"metric": latest.index, "value": latest.values})
    return latest_frame.to_html(index=False, border=0, classes="dataframe")


def _load_registry(path: str | Path) -> list[dict[str, Any]]:
    registry_path = Path(path)
    if not registry_path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in registry_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _fmt_pct(value: Any) -> str:
    if value in ("", None):
        return ""
    return f"{float(value):.2%}"


def _fmt_money(value: Any) -> str:
    if value in ("", None):
        return ""
    return f"${float(value):,.2f}"


def _fmt_float(value: Any) -> str:
    if value in ("", None):
        return ""
    return f"{float(value):.3f}"


def _fmt_generic(value: Any) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if abs(value) < 10 and value != 0:
            return f"{value:.6f}"
        return f"{value:.4f}"
    return str(value)


def _infer_initial_equity(summary: dict[str, Any]) -> float:
    final_equity = float(summary.get("final_equity", 0.0))
    cumulative_return = float(summary.get("cumulative_return", 0.0))
    denominator = 1.0 + cumulative_return
    if abs(denominator) < 1e-12:
        return final_equity
    return final_equity / denominator
