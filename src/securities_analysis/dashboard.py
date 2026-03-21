from __future__ import annotations

import json
import math
from dataclasses import asdict
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd


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

    steps_frame = _prepare_steps_frame(steps_frame)
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
        if entry.get("kind") == "backtest" and artifact_dir.exists():
            try:
                build_backtest_dashboard(artifact_dir)
            except Exception:
                pass

        relative_dashboard = ""
        if dashboard_path.exists():
            relative_dashboard = str(Path("..") / artifact_dir.relative_to("artifacts") / "dashboard.html").replace("\\", "/")

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
            }
        )

    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("created_at", ascending=False)

    html = _render_index_html(frame)
    output.write_text(html, encoding="utf-8")
    return output


def _prepare_steps_frame(steps_frame: pd.DataFrame) -> pd.DataFrame:
    frame = steps_frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["running_max"] = frame["equity"].cummax()
    frame["drawdown"] = frame["equity"] / frame["running_max"] - 1.0
    frame["rolling_vol_20"] = frame["net_return"].rolling(20).std(ddof=1) * math.sqrt(252)
    frame["rolling_turnover_20"] = frame["turnover_fraction"].rolling(20).mean()
    frame["cumulative_gross_return"] = (1.0 + frame["gross_return"]).cumprod() - 1.0
    frame["cumulative_net_return"] = (1.0 + frame["net_return"]).cumprod() - 1.0
    frame["cumulative_cost_drag"] = frame["cost_return"].cumsum()
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
    axes[0].plot(steps_frame["timestamp"], steps_frame["equity"], color="#0b84a5")
    axes[0].set_title(f"{symbol} Equity Curve")
    axes[0].set_ylabel("Equity")
    axes[0].grid(True, alpha=0.25)

    axes[1].fill_between(steps_frame["timestamp"], steps_frame["drawdown"], 0.0, color="#d1495b", alpha=0.35)
    axes[1].set_title("Drawdown")
    axes[1].set_ylabel("Drawdown")
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
    axes[0].set_title("Gross vs Net Cumulative Return")
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
        ("Sharpe Ratio", _fmt_float(risk_report.get("sharpe_ratio"))),
        ("Max Drawdown", _fmt_pct(risk_report.get("max_drawdown"))),
        ("Trades", str(summary.get("trades", ""))),
        ("Warmup Bars", str(summary.get("warmup_bars", ""))),
    ]

    strategy_table = _dict_to_table_rows(strategy_spec)
    risk_table = _dict_to_table_rows(risk_spec)
    cost_table = _dict_to_table_rows(costs)
    risk_metrics_table = _dict_to_table_rows(risk_report)

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


def _render_index_html(frame: pd.DataFrame) -> str:
    rows = []
    for _, row in frame.iterrows():
        dashboard_cell = (
            f"<a href='{escape(str(row['dashboard_href']))}'>open</a>"
            if row["dashboard_href"]
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
            <th>Dashboard</th>
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
