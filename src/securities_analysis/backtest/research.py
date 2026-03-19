from __future__ import annotations

import itertools
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from securities_analysis.backtest.costs import ExecutionCostModel
from securities_analysis.backtest.engine import BacktestResult, StrategyBacktester
from securities_analysis.backtest.reporting import save_backtest_artifacts
from securities_analysis.execution.alpaca import AlpacaTrader
from securities_analysis.risk.metrics import RiskReport, build_risk_report
from securities_analysis.risk.policy import RiskPolicy
from securities_analysis.agents.contracts import Bar
from securities_analysis.strategies.factory import build_strategy


@dataclass(slots=True)
class ResearchRunConfig:
    strategy_family: str
    symbol: str
    asset_class: str
    start: str
    end: str
    period_label: str
    freq: str
    initial_equity: float
    spread_bps: float
    commission_bps: float
    slippage_bps: float
    market_impact_bps_per_turnover: float
    lookback_bars: int
    vol_lookback_bars: int
    target_volatility: float
    max_gross_leverage: float
    max_position_notional_pct: float
    max_trade_notional_pct: float
    max_daily_drawdown_pct: float
    max_spread_bps: float
    fractional_kelly: float
    max_kelly_fraction: float
    allow_short: bool


@dataclass(slots=True)
class ResearchRun:
    config: ResearchRunConfig
    result: BacktestResult
    symbol_buy_hold_report: RiskReport
    symbol_buy_hold_cumulative_return: float
    market_benchmark_symbol: str
    market_buy_hold_report: RiskReport
    market_buy_hold_cumulative_return: float


@dataclass(slots=True)
class ResearchPeriod:
    start: str
    end: str
    label: str


def run_research_grid(
    trader: AlpacaTrader,
    symbols: list[str],
    asset_class: str,
    start: str,
    end: str,
    freq: str,
    initial_equity: float,
    spread_bps: float,
    commission_bps: float,
    slippage_bps: float,
    market_impact_bps_per_turnover: float,
    lookback_bars_grid: list[int],
    vol_lookback_bars_grid: list[int],
    target_volatility_grid: list[float],
    max_gross_leverage_grid: list[float],
    max_position_notional_pct_grid: list[float],
    max_trade_notional_pct_grid: list[float],
    max_daily_drawdown_pct_grid: list[float],
    max_spread_bps_grid: list[float],
    fractional_kelly_grid: list[float],
    max_kelly_fraction_grid: list[float],
    allow_short: bool,
    market_benchmark_symbol: str | None = None,
    strategy_families: list[str] | None = None,
    mean_reversion_entry_zscore: float = 1.0,
    mean_reversion_exit_zscore: float = 0.25,
) -> list[ResearchRun]:
    period = ResearchPeriod(start=start, end=end, label=f"{start}_to_{end}")
    return run_research_periods(
        trader=trader,
        symbols=symbols,
        asset_class=asset_class,
        periods=[period],
        freq=freq,
        initial_equity=initial_equity,
        spread_bps=spread_bps,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        market_impact_bps_per_turnover=market_impact_bps_per_turnover,
        lookback_bars_grid=lookback_bars_grid,
        vol_lookback_bars_grid=vol_lookback_bars_grid,
        target_volatility_grid=target_volatility_grid,
        max_gross_leverage_grid=max_gross_leverage_grid,
        max_position_notional_pct_grid=max_position_notional_pct_grid,
        max_trade_notional_pct_grid=max_trade_notional_pct_grid,
        max_daily_drawdown_pct_grid=max_daily_drawdown_pct_grid,
        max_spread_bps_grid=max_spread_bps_grid,
        fractional_kelly_grid=fractional_kelly_grid,
        max_kelly_fraction_grid=max_kelly_fraction_grid,
        allow_short=allow_short,
        market_benchmark_symbol=market_benchmark_symbol,
        strategy_families=strategy_families,
        mean_reversion_entry_zscore=mean_reversion_entry_zscore,
        mean_reversion_exit_zscore=mean_reversion_exit_zscore,
    )


def run_research_periods(
    trader: AlpacaTrader,
    symbols: list[str],
    asset_class: str,
    periods: list[ResearchPeriod],
    freq: str,
    initial_equity: float,
    spread_bps: float,
    commission_bps: float,
    slippage_bps: float,
    market_impact_bps_per_turnover: float,
    lookback_bars_grid: list[int],
    vol_lookback_bars_grid: list[int],
    target_volatility_grid: list[float],
    max_gross_leverage_grid: list[float],
    max_position_notional_pct_grid: list[float],
    max_trade_notional_pct_grid: list[float],
    max_daily_drawdown_pct_grid: list[float],
    max_spread_bps_grid: list[float],
    fractional_kelly_grid: list[float],
    max_kelly_fraction_grid: list[float],
    allow_short: bool,
    market_benchmark_symbol: str | None = None,
    strategy_families: list[str] | None = None,
    mean_reversion_entry_zscore: float = 1.0,
    mean_reversion_exit_zscore: float = 0.25,
) -> list[ResearchRun]:
    periods_per_year = _periods_per_year_for_freq(freq)
    resolved_market_benchmark_symbol = market_benchmark_symbol or _default_market_benchmark_symbol(asset_class)
    resolved_strategy_families = strategy_families or ["trend"]
    runs: list[ResearchRun] = []
    base_parameter_grid = list(
        itertools.product(
            lookback_bars_grid,
            vol_lookback_bars_grid,
            target_volatility_grid,
            max_gross_leverage_grid,
            max_position_notional_pct_grid,
            max_trade_notional_pct_grid,
            max_daily_drawdown_pct_grid,
            max_spread_bps_grid,
            fractional_kelly_grid,
            max_kelly_fraction_grid,
        )
    )

    for period in periods:
        historical_bars = {
            symbol: trader.get_historical_bar_objects(
                ticker=symbol,
                start=period.start,
                end=period.end,
                freq=freq,
                asset_class=asset_class,
            )
            for symbol in symbols
        }
        market_benchmark_bars = historical_bars.get(resolved_market_benchmark_symbol)
        if market_benchmark_bars is None:
            market_benchmark_bars = trader.get_historical_bar_objects(
                ticker=resolved_market_benchmark_symbol,
                start=period.start,
                end=period.end,
                freq=freq,
                asset_class=asset_class,
            )

        for symbol in symbols:
            bars = historical_bars[symbol]
            for strategy_family in resolved_strategy_families:
                for (
                    lookback_bars,
                    vol_lookback_bars,
                    target_volatility,
                    max_gross_leverage,
                    max_position_notional_pct,
                    max_trade_notional_pct,
                    max_daily_drawdown_pct,
                    max_spread_bps,
                    fractional_kelly,
                    max_kelly_fraction,
                ) in base_parameter_grid:
                    if vol_lookback_bars > lookback_bars + 1000:
                        continue

                    config = ResearchRunConfig(
                        strategy_family=strategy_family,
                        symbol=symbol,
                        asset_class=asset_class,
                        start=period.start,
                        end=period.end,
                        period_label=period.label,
                        freq=freq,
                        initial_equity=initial_equity,
                        spread_bps=spread_bps,
                        commission_bps=commission_bps,
                        slippage_bps=slippage_bps,
                        market_impact_bps_per_turnover=market_impact_bps_per_turnover,
                        lookback_bars=lookback_bars,
                        vol_lookback_bars=vol_lookback_bars,
                        target_volatility=target_volatility,
                        max_gross_leverage=max_gross_leverage,
                        max_position_notional_pct=max_position_notional_pct,
                        max_trade_notional_pct=max_trade_notional_pct,
                        max_daily_drawdown_pct=max_daily_drawdown_pct,
                        max_spread_bps=max_spread_bps,
                        fractional_kelly=fractional_kelly,
                        max_kelly_fraction=max_kelly_fraction,
                        allow_short=allow_short,
                    )

                    strategy = build_strategy(
                        strategy_family=strategy_family,
                        symbol=symbol,
                        lookback_bars=lookback_bars,
                        vol_lookback_bars=vol_lookback_bars,
                        target_volatility=target_volatility,
                        max_gross_leverage=max_gross_leverage,
                        periods_per_year=periods_per_year,
                        allow_short=allow_short,
                        mean_reversion_entry_zscore=mean_reversion_entry_zscore,
                        mean_reversion_exit_zscore=mean_reversion_exit_zscore,
                    )
                    risk_policy = RiskPolicy(
                        periods_per_year=periods_per_year,
                        max_gross_leverage=max_gross_leverage,
                        max_position_notional_pct=max_position_notional_pct,
                        max_trade_notional_pct=max_trade_notional_pct,
                        max_daily_drawdown_pct=max_daily_drawdown_pct,
                        max_spread_bps=max_spread_bps,
                        fractional_kelly=fractional_kelly,
                        max_kelly_fraction=max_kelly_fraction,
                        allow_short=allow_short,
                    )
                    backtester = StrategyBacktester(
                        strategy=strategy,
                        risk_policy=risk_policy,
                        initial_equity=initial_equity,
                        spread_bps=spread_bps,
                        cost_model=ExecutionCostModel(
                            commission_bps=commission_bps,
                            slippage_bps=slippage_bps,
                            market_impact_bps_per_turnover=market_impact_bps_per_turnover,
                        ),
                    )
                    result = backtester.run(bars)
                    symbol_buy_hold_returns = _buy_hold_returns_for_result(bars, result.warmup_bars)
                    market_buy_hold_returns = _buy_hold_returns_for_result(
                        market_benchmark_bars,
                        result.warmup_bars,
                    )
                    runs.append(
                        ResearchRun(
                            config=config,
                            result=result,
                            symbol_buy_hold_report=build_risk_report(symbol_buy_hold_returns, periods_per_year),
                            symbol_buy_hold_cumulative_return=_cumulative_return_from_returns(symbol_buy_hold_returns),
                            market_benchmark_symbol=resolved_market_benchmark_symbol,
                            market_buy_hold_report=build_risk_report(market_buy_hold_returns, periods_per_year),
                            market_buy_hold_cumulative_return=_cumulative_return_from_returns(market_buy_hold_returns),
                        )
                    )
    return runs


def research_runs_to_frame(runs: list[ResearchRun]) -> pd.DataFrame:
    rows: list[dict[str, float | int | str | bool]] = []
    for run in runs:
        report = run.result.risk_report
        rows.append(
            {
                "symbol": run.config.symbol,
                "strategy_family": run.config.strategy_family,
                "period_label": run.config.period_label,
                "start": run.config.start,
                "end": run.config.end,
                "market_benchmark_symbol": run.market_benchmark_symbol,
                "asset_class": run.config.asset_class,
                "freq": run.config.freq,
                "lookback_bars": run.config.lookback_bars,
                "vol_lookback_bars": run.config.vol_lookback_bars,
                "target_volatility": run.config.target_volatility,
                "max_gross_leverage": run.config.max_gross_leverage,
                "max_position_notional_pct": run.config.max_position_notional_pct,
                "max_trade_notional_pct": run.config.max_trade_notional_pct,
                "max_daily_drawdown_pct": run.config.max_daily_drawdown_pct,
                "max_spread_bps": run.config.max_spread_bps,
                "fractional_kelly": run.config.fractional_kelly,
                "max_kelly_fraction": run.config.max_kelly_fraction,
                "allow_short": run.config.allow_short,
                "bars_processed": run.result.bars_processed,
                "warmup_bars": run.result.warmup_bars,
                "trades": run.result.trades,
                "final_equity": run.result.final_equity,
                "cumulative_return": run.result.cumulative_return,
                "symbol_buy_hold_cumulative_return": run.symbol_buy_hold_cumulative_return,
                "market_buy_hold_cumulative_return": run.market_buy_hold_cumulative_return,
                "excess_return_vs_symbol_buy_hold": (
                    run.result.cumulative_return - run.symbol_buy_hold_cumulative_return
                ),
                "excess_return_vs_market_buy_hold": (
                    run.result.cumulative_return - run.market_buy_hold_cumulative_return
                ),
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
                "symbol_buy_hold_sharpe_ratio": run.symbol_buy_hold_report.sharpe_ratio,
                "market_buy_hold_sharpe_ratio": run.market_buy_hold_report.sharpe_ratio,
                "excess_sharpe_vs_symbol_buy_hold": (
                    report.sharpe_ratio - run.symbol_buy_hold_report.sharpe_ratio
                ),
                "excess_sharpe_vs_market_buy_hold": (
                    report.sharpe_ratio - run.market_buy_hold_report.sharpe_ratio
                ),
            }
        )
    return pd.DataFrame(rows)


def dedupe_research_frame(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return leaderboard.copy()

    deduped = leaderboard.copy()
    deduped["behavior_signature"] = deduped.apply(_behavior_signature, axis=1)
    deduped["duplicate_count"] = deduped.groupby("behavior_signature")["behavior_signature"].transform("size")
    deduped = deduped.drop_duplicates(subset=["behavior_signature"]).reset_index(drop=True)
    deduped.insert(0, "deduped_rank", range(1, len(deduped) + 1))
    return deduped


def summarize_research_by_symbol(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()

    summary = (
        leaderboard.groupby("symbol", as_index=False)
        .agg(
            runs=("symbol", "size"),
            best_cumulative_return=("cumulative_return", "max"),
            best_symbol_buy_hold_return=("symbol_buy_hold_cumulative_return", "max"),
            best_market_buy_hold_return=("market_buy_hold_cumulative_return", "max"),
            best_excess_return_vs_symbol_buy_hold=("excess_return_vs_symbol_buy_hold", "max"),
            best_excess_return_vs_market_buy_hold=("excess_return_vs_market_buy_hold", "max"),
            best_sharpe_ratio=("sharpe_ratio", "max"),
            best_symbol_buy_hold_sharpe_ratio=("symbol_buy_hold_sharpe_ratio", "max"),
            best_market_buy_hold_sharpe_ratio=("market_buy_hold_sharpe_ratio", "max"),
            best_excess_sharpe_vs_symbol_buy_hold=("excess_sharpe_vs_symbol_buy_hold", "max"),
            best_excess_sharpe_vs_market_buy_hold=("excess_sharpe_vs_market_buy_hold", "max"),
            median_sharpe_ratio=("sharpe_ratio", "median"),
            best_calmar_ratio=("calmar_ratio", "max"),
            median_max_drawdown=("max_drawdown", "median"),
            min_max_drawdown=("max_drawdown", "max"),
            median_trades=("trades", "median"),
        )
        .sort_values(by="best_sharpe_ratio", ascending=False)
        .reset_index(drop=True)
    )
    summary.insert(0, "rank", range(1, len(summary) + 1))
    return summary


def summarize_research_by_strategy_family(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()

    summary = (
        leaderboard.groupby("strategy_family", as_index=False)
        .agg(
            runs=("strategy_family", "size"),
            symbols_covered=("symbol", "nunique"),
            periods_covered=("period_label", "nunique"),
            best_cumulative_return=("cumulative_return", "max"),
            best_excess_return_vs_symbol_buy_hold=("excess_return_vs_symbol_buy_hold", "max"),
            best_excess_return_vs_market_buy_hold=("excess_return_vs_market_buy_hold", "max"),
            mean_sharpe_ratio=("sharpe_ratio", "mean"),
            mean_excess_sharpe_vs_symbol_buy_hold=("excess_sharpe_vs_symbol_buy_hold", "mean"),
            mean_excess_sharpe_vs_market_buy_hold=("excess_sharpe_vs_market_buy_hold", "mean"),
        )
        .sort_values(by="mean_excess_sharpe_vs_symbol_buy_hold", ascending=False)
        .reset_index(drop=True)
    )
    summary.insert(0, "rank", range(1, len(summary) + 1))
    return summary


def summarize_research_by_strategy_symbol_period(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()

    summary = (
        leaderboard.groupby(["strategy_family", "period_label", "symbol"], as_index=False)
        .agg(
            runs=("symbol", "size"),
            best_cumulative_return=("cumulative_return", "max"),
            best_excess_return_vs_symbol_buy_hold=("excess_return_vs_symbol_buy_hold", "max"),
            best_excess_return_vs_market_buy_hold=("excess_return_vs_market_buy_hold", "max"),
            best_sharpe_ratio=("sharpe_ratio", "max"),
            best_excess_sharpe_vs_symbol_buy_hold=("excess_sharpe_vs_symbol_buy_hold", "max"),
            best_excess_sharpe_vs_market_buy_hold=("excess_sharpe_vs_market_buy_hold", "max"),
        )
        .sort_values(
            by=["strategy_family", "period_label", "best_excess_sharpe_vs_symbol_buy_hold"],
            ascending=[True, True, False],
        )
        .reset_index(drop=True)
    )
    summary.insert(0, "rank", range(1, len(summary) + 1))
    return summary


def summarize_research_by_period(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()

    summary = (
        leaderboard.groupby("period_label", as_index=False)
        .agg(
            runs=("period_label", "size"),
            symbols_covered=("symbol", "nunique"),
            best_cumulative_return=("cumulative_return", "max"),
            best_excess_return_vs_symbol_buy_hold=("excess_return_vs_symbol_buy_hold", "max"),
            best_excess_return_vs_market_buy_hold=("excess_return_vs_market_buy_hold", "max"),
            best_sharpe_ratio=("sharpe_ratio", "max"),
            mean_sharpe_ratio=("sharpe_ratio", "mean"),
            mean_excess_sharpe_vs_symbol_buy_hold=("excess_sharpe_vs_symbol_buy_hold", "mean"),
            mean_excess_sharpe_vs_market_buy_hold=("excess_sharpe_vs_market_buy_hold", "mean"),
            median_max_drawdown=("max_drawdown", "median"),
        )
        .sort_values(by="period_label")
        .reset_index(drop=True)
    )
    summary.insert(0, "rank", range(1, len(summary) + 1))
    return summary


def summarize_research_by_symbol_period(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()

    summary = (
        leaderboard.groupby(["period_label", "symbol"], as_index=False)
        .agg(
            runs=("symbol", "size"),
            best_cumulative_return=("cumulative_return", "max"),
            best_excess_return_vs_symbol_buy_hold=("excess_return_vs_symbol_buy_hold", "max"),
            best_excess_return_vs_market_buy_hold=("excess_return_vs_market_buy_hold", "max"),
            best_sharpe_ratio=("sharpe_ratio", "max"),
            best_excess_sharpe_vs_symbol_buy_hold=("excess_sharpe_vs_symbol_buy_hold", "max"),
            best_excess_sharpe_vs_market_buy_hold=("excess_sharpe_vs_market_buy_hold", "max"),
            median_sharpe_ratio=("sharpe_ratio", "median"),
            median_max_drawdown=("max_drawdown", "median"),
        )
        .sort_values(by=["period_label", "best_sharpe_ratio"], ascending=[True, False])
        .reset_index(drop=True)
    )
    summary.insert(0, "rank", range(1, len(summary) + 1))
    return summary


def summarize_research_by_parameters(leaderboard: pd.DataFrame) -> pd.DataFrame:
    if leaderboard.empty:
        return pd.DataFrame()

    parameter_columns = [
        "lookback_bars",
        "vol_lookback_bars",
        "target_volatility",
        "fractional_kelly",
        "max_kelly_fraction",
        "max_position_notional_pct",
        "max_trade_notional_pct",
        "max_daily_drawdown_pct",
    ]
    summary = (
        leaderboard.groupby(parameter_columns, as_index=False)
        .agg(
            runs=("symbol", "size"),
            symbols_covered=("symbol", "nunique"),
            mean_cumulative_return=("cumulative_return", "mean"),
            mean_excess_return_vs_symbol_buy_hold=("excess_return_vs_symbol_buy_hold", "mean"),
            mean_excess_return_vs_market_buy_hold=("excess_return_vs_market_buy_hold", "mean"),
            mean_sharpe_ratio=("sharpe_ratio", "mean"),
            mean_excess_sharpe_vs_symbol_buy_hold=("excess_sharpe_vs_symbol_buy_hold", "mean"),
            mean_excess_sharpe_vs_market_buy_hold=("excess_sharpe_vs_market_buy_hold", "mean"),
            best_sharpe_ratio=("sharpe_ratio", "max"),
            mean_calmar_ratio=("calmar_ratio", "mean"),
            median_max_drawdown=("max_drawdown", "median"),
        )
        .sort_values(by=["mean_sharpe_ratio", "best_sharpe_ratio"], ascending=False)
        .reset_index(drop=True)
    )
    summary.insert(0, "rank", range(1, len(summary) + 1))
    return summary


def save_research_artifacts(
    runs: list[ResearchRun],
    output_dir: str | Path,
    rank_by: str,
    top_n: int = 10,
    save_top_run_artifacts: bool = False,
) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    leaderboard = research_runs_to_frame(runs)
    if leaderboard.empty:
        raise ValueError("No research runs were produced.")

    leaderboard = leaderboard.sort_values(by=rank_by, ascending=False).reset_index(drop=True)
    leaderboard.insert(0, "rank", range(1, len(leaderboard) + 1))
    deduped_leaderboard = dedupe_research_frame(leaderboard)
    symbol_summary = summarize_research_by_symbol(leaderboard)
    strategy_family_summary = summarize_research_by_strategy_family(leaderboard)
    period_summary = summarize_research_by_period(leaderboard)
    symbol_period_summary = summarize_research_by_symbol_period(leaderboard)
    strategy_symbol_period_summary = summarize_research_by_strategy_symbol_period(leaderboard)
    parameter_summary = summarize_research_by_parameters(leaderboard)

    summary_payload = {
        "runs": len(runs),
        "periods": sorted({run.config.period_label for run in runs}),
        "rank_by": rank_by,
        "top_n": top_n,
        "best_run": leaderboard.iloc[0].to_dict(),
        "best_unique_run": deduped_leaderboard.iloc[0].to_dict() if not deduped_leaderboard.empty else None,
    }
    (artifact_dir / "summary.json").write_text(
        json.dumps(summary_payload, indent=2, default=str),
        encoding="utf-8",
    )
    leaderboard.to_csv(artifact_dir / "leaderboard.csv", index=False)
    deduped_leaderboard.to_csv(artifact_dir / "leaderboard_deduped.csv", index=False)
    symbol_summary.to_csv(artifact_dir / "summary_by_symbol.csv", index=False)
    strategy_family_summary.to_csv(artifact_dir / "summary_by_strategy_family.csv", index=False)
    period_summary.to_csv(artifact_dir / "summary_by_period.csv", index=False)
    symbol_period_summary.to_csv(artifact_dir / "summary_by_symbol_period.csv", index=False)
    strategy_symbol_period_summary.to_csv(artifact_dir / "summary_by_strategy_symbol_period.csv", index=False)
    parameter_summary.to_csv(artifact_dir / "summary_by_parameters.csv", index=False)
    leaderboard.head(top_n).to_json(
        artifact_dir / "leaderboard_top.json",
        orient="records",
        indent=2,
    )
    deduped_leaderboard.head(top_n).to_json(
        artifact_dir / "leaderboard_deduped_top.json",
        orient="records",
        indent=2,
    )

    if save_top_run_artifacts:
        ranked_runs = _sort_runs(runs, rank_by=rank_by)
        for index, run in enumerate(ranked_runs[:top_n], start=1):
            run_dir = artifact_dir / f"rank_{index:02d}_{run.config.symbol}"
            save_backtest_artifacts(run.result, run_dir)
            (run_dir / "config.json").write_text(
                json.dumps(asdict(run.config), indent=2),
                encoding="utf-8",
            )

    return artifact_dir


def _sort_runs(runs: list[ResearchRun], rank_by: str) -> list[ResearchRun]:
    return sorted(
        runs,
        key=lambda run: _rank_value(run, rank_by),
        reverse=True,
    )


def _rank_value(run: ResearchRun, rank_by: str) -> float:
    if rank_by == "excess_return_vs_symbol_buy_hold":
        return float(run.result.cumulative_return - run.symbol_buy_hold_cumulative_return)
    if rank_by == "excess_return_vs_market_buy_hold":
        return float(run.result.cumulative_return - run.market_buy_hold_cumulative_return)
    if rank_by == "excess_sharpe_vs_symbol_buy_hold":
        return float(run.result.risk_report.sharpe_ratio - run.symbol_buy_hold_report.sharpe_ratio)
    if rank_by == "excess_sharpe_vs_market_buy_hold":
        return float(run.result.risk_report.sharpe_ratio - run.market_buy_hold_report.sharpe_ratio)
    if hasattr(run.result.risk_report, rank_by):
        return float(getattr(run.result.risk_report, rank_by))
    if hasattr(run.result, rank_by):
        return float(getattr(run.result, rank_by))
    raise ValueError(f"Unsupported rank_by metric: {rank_by}")


def _periods_per_year_for_freq(freq: str) -> int:
    mapping = {
        "minute": int(252 * 6.5 * 60),
        "hour": int(252 * 6.5),
        "day": 252,
        "week": 52,
        "month": 12,
    }
    return mapping[freq]


def _behavior_signature(row: pd.Series) -> str:
    components = [
        row["symbol"],
        int(row["bars_processed"]),
        int(row["warmup_bars"]),
        int(row["trades"]),
        round(float(row["cumulative_return"]), 8),
        round(float(row["annual_return"]), 8),
        round(float(row["annual_volatility"]), 8),
        round(float(row["sharpe_ratio"]), 8),
        round(float(row["sortino_ratio"]), 8),
        round(float(row["max_drawdown"]), 8),
        round(float(row["calmar_ratio"]), 8),
        round(float(row["profit_factor"]), 8),
        round(float(row["stability"]), 8),
    ]
    return "|".join(str(component) for component in components)


def _buy_hold_returns_for_result(bars: list[Bar], warmup_bars: int) -> np.ndarray:
    if len(bars) < 2:
        return np.array([], dtype=float)
    closes = np.array([bar.close_price for bar in bars], dtype=float)
    log_returns = np.diff(np.log(closes))
    start_index = max(warmup_bars - 1, 0)
    return log_returns[start_index:]


def _cumulative_return_from_returns(returns: np.ndarray) -> float:
    if returns.size == 0:
        return 0.0
    return float(np.exp(np.sum(returns)) - 1.0)


def _default_market_benchmark_symbol(asset_class: str) -> str:
    if asset_class == "crypto":
        return "BTC/USD"
    return "SPY"
