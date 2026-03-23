from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from securities_analysis.agents.contracts import Bar
from securities_analysis.backtest.costs import ExecutionCostModel
from securities_analysis.backtest.engine import BacktestResult, BacktestStep
from securities_analysis.dashboard import build_backtest_dashboard
from securities_analysis.execution.history import HistoricalPriceProvider
from securities_analysis.risk.metrics import build_risk_report


@dataclass(slots=True)
class PanelBacktestConfig:
    horizon_bars: int
    top_k: int = 3
    rebalance_every_dates: int = 5
    initial_equity: float = 100_000.0
    target_gross_leverage: float = 1.0
    long_threshold: float = 0.0
    allow_short: bool = False
    spread_bps: float = 0.0
    periods_per_year: int = 252
    commission_bps: float = 0.0
    slippage_bps: float = 2.0
    market_impact_bps_per_turnover: float = 5.0
    market_benchmark_symbol: str | None = "SPY"


def evaluate_panel_prediction_backtest(
    predictions_frame: pd.DataFrame,
    *,
    config: PanelBacktestConfig,
    market_benchmark_frame: pd.DataFrame | None = None,
) -> BacktestResult:
    working = predictions_frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    working = working.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

    prediction_column = f"panel_pred_h{config.horizon_bars}"
    if prediction_column not in working.columns:
        raise KeyError(f"Predictions frame missing required column: {prediction_column}")

    close_frame = (
        working.pivot(index="timestamp", columns="symbol", values="close_price")
        .astype(float)
        .sort_index()
    )
    prediction_matrix = (
        working.pivot(index="timestamp", columns="symbol", values=prediction_column)
        .sort_index()
    )

    simple_returns = close_frame.pct_change(fill_method=None)
    dates = list(close_frame.index)
    if len(dates) < 3:
        raise ValueError("Not enough dates in the panel predictions to backtest.")

    equity = float(config.initial_equity)
    benchmark_equity = float(config.initial_equity)
    market_benchmark_equity = float(config.initial_equity)
    current_weights = pd.Series(0.0, index=close_frame.columns, dtype=float)
    steps: list[BacktestStep] = []
    net_returns: list[float] = []
    trades = 0

    cost_model = ExecutionCostModel(
        commission_bps=config.commission_bps,
        slippage_bps=config.slippage_bps,
        market_impact_bps_per_turnover=config.market_impact_bps_per_turnover,
    )

    rebalance_counter = 0
    started = False
    benchmark_returns = _aligned_market_benchmark_returns(
        market_benchmark_frame=market_benchmark_frame,
        aligned_dates=dates,
    )

    for idx in range(len(dates) - 1):
        current_date = dates[idx]
        next_date = dates[idx + 1]
        forecast_row = prediction_matrix.loc[current_date]
        current_close = close_frame.loc[current_date]
        next_returns = simple_returns.loc[next_date].fillna(0.0)

        should_rebalance = (rebalance_counter % max(config.rebalance_every_dates, 1) == 0)
        target_weights = current_weights.copy()
        selected_symbols: list[str] = []

        if should_rebalance:
            target_weights, selected_symbols = _select_target_weights(
                forecast_row=forecast_row,
                universe_columns=list(close_frame.columns),
                top_k=config.top_k,
                target_gross_leverage=config.target_gross_leverage,
                long_threshold=config.long_threshold,
                allow_short=config.allow_short,
            )
            started = started or bool(selected_symbols)
        else:
            selected_symbols = current_weights.loc[current_weights.abs() > 1e-12].index.tolist()

        turnover_fraction = float(np.abs(target_weights - current_weights).sum())
        if turnover_fraction > 1e-10:
            trades += 1

        current_weights = target_weights
        gross_return = float((current_weights * next_returns).sum())
        cost_return = cost_model.estimate_cost_return(
            turnover_fraction=turnover_fraction,
            spread_bps=config.spread_bps,
        )
        net_return = gross_return - cost_return
        net_returns.append(net_return)

        buy_hold_return = float(next_returns.mean())
        benchmark_equity *= 1.0 + buy_hold_return
        market_benchmark_return = float(benchmark_returns.loc[next_date]) if benchmark_returns is not None and next_date in benchmark_returns.index else 0.0
        market_benchmark_equity *= 1.0 + market_benchmark_return
        equity *= 1.0 + net_return

        aggregate_score = float(np.nanmean(forecast_row.astype(float))) if forecast_row.notna().any() else 0.0
        top_forecast = float(
            forecast_row.loc[selected_symbols].mean()
        ) if selected_symbols else 0.0

        benchmark_index_level = benchmark_equity / max(config.initial_equity, 1e-8) * 100.0
        steps.append(
            BacktestStep(
                bar=Bar(
                    symbol=f"PANEL_H{config.horizon_bars}",
                    start_time=_to_datetime(current_date),
                    end_time=_to_datetime(next_date),
                    open_price=benchmark_index_level / max(1.0 + buy_hold_return, 1e-8),
                    high_price=benchmark_index_level,
                    low_price=benchmark_index_level,
                    close_price=benchmark_index_level,
                    volume=None,
                    source="panel_predictions",
                ),
                signal_name=f"panel_rank_h{config.horizon_bars}",
                signal_confidence=float(abs(top_forecast)),
                signal_rationale=(
                    f"Equal-weight top {len(selected_symbols)} forecasts at horizon {config.horizon_bars}"
                    if selected_symbols else
                    f"No forecasts above threshold {config.long_threshold:.4f}; stay flat"
                ),
                approved=bool(selected_symbols),
                reason="Approved" if selected_symbols else "No eligible forecasts",
                target_position=float(np.abs(current_weights).sum()),
                desired_quantity=float(len(selected_symbols)),
                equity=equity,
                session_return=0.0,
                signal_metadata={
                    "aggregate_score": aggregate_score,
                    f"h{config.horizon_bars}_expected_return": top_forecast,
                    "buy_hold_cumulative_return": benchmark_equity / max(config.initial_equity, 1e-8) - 1.0,
                    "market_buy_hold_cumulative_return": market_benchmark_equity / max(config.initial_equity, 1e-8) - 1.0,
                    "active_symbols": ",".join(selected_symbols),
                    "gross_exposure": float(np.abs(current_weights).sum()),
                    "net_exposure": float(current_weights.sum()),
                },
                spread_bps=config.spread_bps,
                turnover_fraction=turnover_fraction,
                gross_return=gross_return,
                cost_return=cost_return,
                net_return=net_return,
            )
        )
        rebalance_counter += 1

    report = build_risk_report(np.asarray(net_returns, dtype=float), periods_per_year=config.periods_per_year)
    return BacktestResult(
        symbol=f"PANEL_H{config.horizon_bars}",
        bars_processed=len(steps),
        warmup_bars=0,
        trades=trades,
        final_equity=equity,
        cumulative_return=equity / max(config.initial_equity, 1e-8) - 1.0,
        risk_report=report,
        steps=steps,
    )


def save_panel_backtest_artifacts(
    result: BacktestResult,
    *,
    output_dir: str | Path,
    metadata: dict[str, Any] | None = None,
) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

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
    (artifact_dir / "summary.json").write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    steps_frame = pd.DataFrame([_step_to_record(step) for step in result.steps])
    steps_frame.to_csv(artifact_dir / "steps.csv", index=False)
    build_backtest_dashboard(artifact_dir)
    return artifact_dir


def default_panel_backtest_output_dir() -> Path:
    stamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "backtests" / f"panel_portfolio_{stamp}"


def load_panel_predictions(forecast_dir: str | Path) -> pd.DataFrame:
    return pd.read_csv(Path(forecast_dir) / "panel_predictions.csv")


def load_market_benchmark_frame(
    *,
    history_provider: HistoricalPriceProvider,
    symbol: str,
    dates: list[pd.Timestamp],
    freq: str = "day",
) -> pd.DataFrame:
    if not dates:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    start = pd.Timestamp(min(dates)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(max(dates)) + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    frame = history_provider.get_historical_prices(
        ticker=symbol,
        start=start,
        end=end,
        freq=freq,
        asset_class="equity",
    )
    if frame.empty:
        cached = _load_cached_yfinance_frame(
            history_provider=history_provider,
            symbol=symbol,
            start=start,
            end=end,
            freq=freq,
        )
        if cached is not None:
            frame = cached
    if frame.empty:
        return frame
    working = frame.copy()
    working.index = pd.to_datetime(working.index, utc=True)
    return working.sort_index()


def _select_target_weights(
    *,
    forecast_row: pd.Series,
    universe_columns: list[str],
    top_k: int,
    target_gross_leverage: float,
    long_threshold: float,
    allow_short: bool,
) -> tuple[pd.Series, list[str]]:
    forecasts = pd.to_numeric(forecast_row, errors="coerce").dropna()
    weights = pd.Series(0.0, index=universe_columns, dtype=float)
    if forecasts.empty:
        return weights, []

    selected_symbols: list[str] = []
    if allow_short:
        longs = forecasts[forecasts > long_threshold].sort_values(ascending=False).head(top_k)
        shorts = forecasts[forecasts < -long_threshold].sort_values(ascending=True).head(top_k)
        gross_half = target_gross_leverage / 2.0
        if not longs.empty:
            weights.loc[longs.index] = gross_half / len(longs)
            selected_symbols.extend(longs.index.tolist())
        if not shorts.empty:
            weights.loc[shorts.index] = -gross_half / len(shorts)
            selected_symbols.extend(shorts.index.tolist())
        return weights, selected_symbols

    longs = forecasts[forecasts > long_threshold].sort_values(ascending=False).head(top_k)
    if longs.empty:
        return weights, []
    weights.loc[longs.index] = target_gross_leverage / len(longs)
    return weights, longs.index.tolist()


def _step_to_record(step: BacktestStep) -> dict[str, Any]:
    payload: dict[str, Any] = {
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
        if isinstance(value, (str, int, float, bool)) or value is None:
            payload[key] = value
    return payload


def _to_datetime(value: pd.Timestamp) -> datetime:
    return value.to_pydatetime()


def _aligned_market_benchmark_returns(
    *,
    market_benchmark_frame: pd.DataFrame | None,
    aligned_dates: list[pd.Timestamp],
) -> pd.Series | None:
    if market_benchmark_frame is None or market_benchmark_frame.empty or not aligned_dates:
        return None
    benchmark = market_benchmark_frame.copy()
    benchmark = benchmark.sort_index()
    benchmark.index = pd.to_datetime(benchmark.index, utc=True)
    benchmark_close = pd.to_numeric(benchmark["close"], errors="coerce")
    aligned_index = pd.DatetimeIndex(aligned_dates)
    aligned_close = benchmark_close.reindex(aligned_index).ffill()
    if aligned_close.isna().all():
        return None
    return aligned_close.pct_change(fill_method=None).fillna(0.0)


def _load_cached_yfinance_frame(
    *,
    history_provider: HistoricalPriceProvider,
    symbol: str,
    start: str,
    end: str,
    freq: str,
) -> pd.DataFrame | None:
    cache_dir = getattr(history_provider, "cache_dir", None)
    if cache_dir is None:
        return None
    safe_symbol = symbol.replace("/", "_").replace("^", "caret_").replace("=", "_")
    candidates = sorted(Path(cache_dir).glob(f"{safe_symbol}_*_{freq}.csv"))
    if not candidates:
        return None
    requested_start = pd.Timestamp(start)
    requested_end = pd.Timestamp(end)
    for candidate in candidates:
        parts = candidate.stem.split("_")
        if len(parts) < 4:
            continue
        candidate_start = pd.Timestamp(parts[-3])
        candidate_end = pd.Timestamp(parts[-2])
        if candidate_start <= requested_start and candidate_end >= requested_end:
            frame = pd.read_csv(candidate, parse_dates=["timestamp"]).set_index("timestamp")
            return frame
    frame = pd.read_csv(candidates[-1], parse_dates=["timestamp"]).set_index("timestamp")
    return frame
