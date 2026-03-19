from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from securities_analysis.backtest.costs import ExecutionCostModel
from securities_analysis.backtest.engine import StrategyBacktester
from securities_analysis.backtest.reporting import save_backtest_artifacts
from securities_analysis.backtest.research import ResearchPeriod, save_research_artifacts
from securities_analysis.backtest.research import run_research_grid, run_research_periods
from securities_analysis.config import load_alpaca_settings
from securities_analysis.experiments import new_run_id, write_run_manifest
from securities_analysis.execution.alpaca import AlpacaTrader
from securities_analysis.runtime import risk_spec_from_args, runtime_spec_from_args
from securities_analysis.runtime import strategy_spec_from_args
from securities_analysis.services.mvp_execution import MvpExecutionService
from securities_analysis.services.paper_trading import PaperTradingService
from securities_analysis.strategies import StrategyProtocol, build_strategy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Securities Analysis CLI")
    parser.add_argument(
        "--cfg",
        help="Optional path to a legacy Alpaca .cfg file. "
        "If omitted, environment variables are used.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("account", help="Print paper-trading account details")

    stream_parser = subparsers.add_parser("stream", help="Stream quotes and print aggregated bars")
    stream_parser.add_argument("--symbol", required=True, help="Ticker or crypto pair")
    stream_parser.add_argument(
        "--asset-class",
        default="equity",
        choices=["equity", "crypto"],
        help="Asset class for the symbol",
    )
    stream_parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Bar aggregation interval in seconds",
    )

    mvp_parser = subparsers.add_parser(
        "mvp",
        help="Run the MVP trend-following execution loop",
    )
    mvp_parser.add_argument("--symbol", required=True, help="Ticker or crypto pair")
    mvp_parser.add_argument(
        "--strategy-family",
        default="trend",
        choices=["trend", "mean_reversion"],
        help="Strategy family to run in the live or dry-run loop",
    )
    mvp_parser.add_argument(
        "--asset-class",
        default="equity",
        choices=["equity", "crypto"],
        help="Asset class for the symbol",
    )
    mvp_parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Bar aggregation interval in seconds",
    )
    mvp_parser.add_argument(
        "--live-orders",
        action="store_true",
        help="Actually submit orders instead of printing dry-run intents",
    )
    mvp_parser.add_argument("--warmup-start", help="Optional historical warmup start date YYYY-MM-DD")
    mvp_parser.add_argument("--warmup-end", help="Optional historical warmup end date YYYY-MM-DD")
    mvp_parser.add_argument(
        "--warmup-freq",
        default="minute",
        choices=["minute", "hour", "day", "week", "month"],
        help="Historical warmup bar frequency",
    )

    backtest_parser = subparsers.add_parser(
        "backtest",
        help="Run an offline backtest using the same strategy and risk policy",
    )
    backtest_parser.add_argument("--symbol", required=True, help="Ticker or crypto pair")
    backtest_parser.add_argument(
        "--strategy-family",
        default="trend",
        choices=["trend", "mean_reversion"],
        help="Strategy family to evaluate in the backtest",
    )
    backtest_parser.add_argument(
        "--asset-class",
        default="equity",
        choices=["equity", "crypto"],
        help="Asset class for the symbol",
    )
    backtest_parser.add_argument("--start", required=True, help="Historical start date YYYY-MM-DD")
    backtest_parser.add_argument("--end", required=True, help="Historical end date YYYY-MM-DD")
    backtest_parser.add_argument(
        "--freq",
        default="day",
        choices=["minute", "hour", "day", "week", "month"],
        help="Historical bar frequency",
    )
    backtest_parser.add_argument(
        "--initial-equity",
        type=float,
        default=100000.0,
        help="Starting equity for the backtest",
    )
    backtest_parser.add_argument(
        "--spread-bps",
        type=float,
        default=0.0,
        help="Synthetic spread used in the backtest",
    )
    backtest_parser.add_argument(
        "--commission-bps",
        type=float,
        default=0.0,
        help="Commission cost in basis points",
    )
    backtest_parser.add_argument(
        "--slippage-bps",
        type=float,
        default=2.0,
        help="Base slippage estimate in basis points",
    )
    backtest_parser.add_argument(
        "--market-impact-bps-per-turnover",
        type=float,
        default=5.0,
        help="Extra basis points charged per 1.0x equity turnover",
    )
    backtest_parser.add_argument(
        "--output-dir",
        help="Optional output directory for saved backtest artifacts",
    )
    research_parser = subparsers.add_parser(
        "research",
        help="Run a batch parameter sweep across symbols and save a ranked leaderboard",
    )
    research_parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated symbols, e.g. SPY,QQQ,IWM",
    )
    research_parser.add_argument(
        "--strategy-families",
        default="trend,mean_reversion",
        help="Comma-separated strategy families to compare, e.g. trend,mean_reversion",
    )
    research_parser.add_argument(
        "--asset-class",
        default="equity",
        choices=["equity", "crypto"],
        help="Asset class for all symbols in the sweep",
    )
    research_parser.add_argument("--start", help="Historical start date YYYY-MM-DD")
    research_parser.add_argument("--end", help="Historical end date YYYY-MM-DD")
    research_parser.add_argument(
        "--periods",
        help="Optional comma-separated periods in START:END form. Example: 2023-01-01:2023-12-31,2024-01-01:2024-12-31",
    )
    research_parser.add_argument(
        "--freq",
        default="day",
        choices=["minute", "hour", "day", "week", "month"],
        help="Historical bar frequency",
    )
    research_parser.add_argument(
        "--initial-equity",
        type=float,
        default=100000.0,
        help="Starting equity for each backtest run",
    )
    research_parser.add_argument(
        "--spread-bps",
        type=float,
        default=0.0,
        help="Synthetic spread used in each backtest",
    )
    research_parser.add_argument(
        "--commission-bps",
        type=float,
        default=0.0,
        help="Commission cost in basis points",
    )
    research_parser.add_argument(
        "--slippage-bps",
        type=float,
        default=2.0,
        help="Base slippage estimate in basis points",
    )
    research_parser.add_argument(
        "--market-impact-bps-per-turnover",
        type=float,
        default=5.0,
        help="Extra basis points charged per 1.0x equity turnover",
    )
    research_parser.add_argument(
        "--lookback-bars-grid",
        default="20,30,60",
        help="Comma-separated momentum lookback values",
    )
    research_parser.add_argument(
        "--vol-lookback-bars-grid",
        default="10,20,30",
        help="Comma-separated volatility lookback values",
    )
    research_parser.add_argument(
        "--target-volatility-grid",
        default="0.10,0.20",
        help="Comma-separated annual target vol values",
    )
    research_parser.add_argument(
        "--max-gross-leverage-grid",
        default="1.0",
        help="Comma-separated leverage caps",
    )
    research_parser.add_argument(
        "--max-position-notional-pct-grid",
        default="0.10,0.20",
        help="Comma-separated max position notional fractions",
    )
    research_parser.add_argument(
        "--max-trade-notional-pct-grid",
        default="0.05,0.10",
        help="Comma-separated max trade notional fractions",
    )
    research_parser.add_argument(
        "--max-daily-drawdown-pct-grid",
        default="0.02,0.03",
        help="Comma-separated daily drawdown thresholds",
    )
    research_parser.add_argument(
        "--max-spread-bps-grid",
        default="20.0",
        help="Comma-separated spread filter thresholds",
    )
    research_parser.add_argument(
        "--fractional-kelly-grid",
        default="0.10,0.25",
        help="Comma-separated fractional Kelly values",
    )
    research_parser.add_argument(
        "--max-kelly-fraction-grid",
        default="0.25,0.50",
        help="Comma-separated Kelly caps",
    )
    research_parser.add_argument(
        "--rank-by",
        default="sharpe_ratio",
        choices=[
            "annual_return",
            "cumulative_return",
            "excess_return_vs_symbol_buy_hold",
            "excess_return_vs_market_buy_hold",
            "sharpe_ratio",
            "excess_sharpe_vs_symbol_buy_hold",
            "excess_sharpe_vs_market_buy_hold",
            "sortino_ratio",
            "calmar_ratio",
            "max_drawdown",
            "stability",
            "profit_factor",
        ],
        help="Metric used to rank research runs",
    )
    research_parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="How many top runs to print and save in detail",
    )
    research_parser.add_argument(
        "--output-dir",
        help="Optional output directory for research artifacts",
    )
    research_parser.add_argument(
        "--save-top-run-artifacts",
        action="store_true",
        help="Save full backtest artifacts for the top ranked runs",
    )
    research_parser.add_argument(
        "--market-benchmark-symbol",
        help="Optional benchmark symbol for market buy-and-hold comparison. Defaults to SPY for equities.",
    )
    for parser_obj in (mvp_parser, backtest_parser, research_parser):
        _add_shared_strategy_and_risk_args(parser_obj)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = load_alpaca_settings(cfg_path=args.cfg)
    trader = AlpacaTrader(settings)

    if args.command == "account":
        account = trader.get_account_details()
        print(account)
        return

    if args.command == "stream":
        service = PaperTradingService(
            trader=trader,
            symbol=args.symbol,
            asset_class=args.asset_class,
            interval_seconds=args.interval_seconds,
        )
        service.print_account_summary()
        service.run_quote_stream()
        return

    if args.command == "mvp":
        periods_per_year = max(int((252 * 6.5 * 60) / max(args.interval_seconds, 1)), 1)
        runtime_spec = runtime_spec_from_args(args, periods_per_year)
        strategy = runtime_spec.strategy.build(symbol=args.symbol, periods_per_year=periods_per_year)
        risk_policy = runtime_spec.risk.build()
        service = MvpExecutionService(
            trader=trader,
            strategy=strategy,
            risk_policy=risk_policy,
            symbol=args.symbol,
            asset_class=args.asset_class,
            interval_seconds=args.interval_seconds,
            runtime_spec=runtime_spec,
            dry_run=not args.live_orders,
            warmup_start=args.warmup_start,
            warmup_end=args.warmup_end,
            warmup_freq=args.warmup_freq,
        )
        service.run()
        return

    if args.command == "backtest":
        periods_per_year = _periods_per_year_for_freq(args.freq)
        strategy_spec = strategy_spec_from_args(args)
        risk_spec = risk_spec_from_args(args, periods_per_year)
        strategy = strategy_spec.build(symbol=args.symbol, periods_per_year=periods_per_year)
        risk_policy = risk_spec.build()
        bars = trader.get_historical_bar_objects(
            ticker=args.symbol,
            start=args.start,
            end=args.end,
            freq=args.freq,
            asset_class=args.asset_class,
        )
        result = StrategyBacktester(
            strategy=strategy,
            risk_policy=risk_policy,
            initial_equity=args.initial_equity,
            spread_bps=args.spread_bps,
            cost_model=ExecutionCostModel(
                commission_bps=args.commission_bps,
                slippage_bps=args.slippage_bps,
                market_impact_bps_per_turnover=args.market_impact_bps_per_turnover,
            ),
        ).run(bars)
        report = result.risk_report
        run_id = new_run_id("backtest")
        metadata = {
            "run_id": run_id,
            "runtime_spec": {
                "strategy": strategy_spec.to_dict(),
                "risk": risk_spec.to_dict(),
            },
            "costs": {
                "spread_bps": args.spread_bps,
                "commission_bps": args.commission_bps,
                "slippage_bps": args.slippage_bps,
                "market_impact_bps_per_turnover": args.market_impact_bps_per_turnover,
            },
        }
        print(
            "BACKTEST RESULT | "
            f"symbol={result.symbol} "
            f"bars={result.bars_processed} "
            f"warmup={result.warmup_bars} "
            f"trades={result.trades} "
            f"final_equity={result.final_equity:.2f} "
            f"cum_return={result.cumulative_return:.2%}"
        )
        print(f"RUNTIME SPEC | {strategy_spec.describe()} | risk[{risk_spec.describe()}]")
        print(
            "RISK REPORT | "
            f"sharpe={report.sharpe_ratio:.3f} "
            f"sortino={report.sortino_ratio:.3f} "
            f"calmar={report.calmar_ratio:.3f} "
            f"mdd={report.max_drawdown:.3%} "
            f"var95={report.value_at_risk_95:.5f} "
            f"es95={report.expected_shortfall_95:.5f} "
            f"stability={report.stability:.3f}"
        )
        output_dir = args.output_dir or _default_backtest_output_dir(
            symbol=args.symbol,
            start=args.start,
            end=args.end,
            freq=args.freq,
        )
        artifact_dir = save_backtest_artifacts(result, output_dir, metadata=metadata)
        write_run_manifest(
            artifact_dir,
            kind="backtest",
            run_id=run_id,
            config={
                "symbol": args.symbol,
                "asset_class": args.asset_class,
                "start": args.start,
                "end": args.end,
                "freq": args.freq,
                "initial_equity": args.initial_equity,
                "runtime_spec": metadata["runtime_spec"],
                "costs": metadata["costs"],
            },
            summary={
                "final_equity": result.final_equity,
                "cumulative_return": result.cumulative_return,
                "sharpe_ratio": report.sharpe_ratio,
                "max_drawdown": report.max_drawdown,
                "artifact_dir": str(artifact_dir),
            },
        )
        print(f"ARTIFACTS SAVED | path={artifact_dir}")
        return

    if args.command == "research":
        symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
        if args.periods:
            periods = _parse_periods_arg(args.periods)
        else:
            if not args.start or not args.end:
                parser.error("research requires either --periods or both --start and --end")
            periods = [ResearchPeriod(start=args.start, end=args.end, label=f"{args.start}_to_{args.end}")]
        runs = run_research_periods(
            trader=trader,
            symbols=symbols,
            asset_class=args.asset_class,
            periods=periods,
            freq=args.freq,
            initial_equity=args.initial_equity,
            spread_bps=args.spread_bps,
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
            market_impact_bps_per_turnover=args.market_impact_bps_per_turnover,
            lookback_bars_grid=_parse_int_grid(args.lookback_bars_grid),
            vol_lookback_bars_grid=_parse_int_grid(args.vol_lookback_bars_grid),
            target_volatility_grid=_parse_float_grid(args.target_volatility_grid),
            max_gross_leverage_grid=_parse_float_grid(args.max_gross_leverage_grid),
            max_position_notional_pct_grid=_parse_float_grid(args.max_position_notional_pct_grid),
            max_trade_notional_pct_grid=_parse_float_grid(args.max_trade_notional_pct_grid),
            max_daily_drawdown_pct_grid=_parse_float_grid(args.max_daily_drawdown_pct_grid),
            max_spread_bps_grid=_parse_float_grid(args.max_spread_bps_grid),
            fractional_kelly_grid=_parse_float_grid(args.fractional_kelly_grid),
            max_kelly_fraction_grid=_parse_float_grid(args.max_kelly_fraction_grid),
            allow_short=args.allow_short,
            market_benchmark_symbol=args.market_benchmark_symbol,
            strategy_families=_parse_str_list(args.strategy_families),
            mean_reversion_entry_zscore=args.mean_reversion_entry_zscore,
            mean_reversion_exit_zscore=args.mean_reversion_exit_zscore,
        )
        artifact_dir = save_research_artifacts(
            runs=runs,
            output_dir=args.output_dir or _default_research_output_dir(periods, args.freq),
            rank_by=args.rank_by,
            top_n=args.top_n,
            save_top_run_artifacts=args.save_top_run_artifacts,
        )
        run_id = new_run_id("research")
        write_run_manifest(
            artifact_dir,
            kind="research_sweep",
            run_id=run_id,
            config={
                "symbols": symbols,
                "strategy_families": _parse_str_list(args.strategy_families),
                "periods": [
                    {"start": period.start, "end": period.end, "label": period.label}
                    for period in periods
                ],
                "asset_class": args.asset_class,
                "freq": args.freq,
                "initial_equity": args.initial_equity,
                "costs": {
                    "spread_bps": args.spread_bps,
                    "commission_bps": args.commission_bps,
                    "slippage_bps": args.slippage_bps,
                    "market_impact_bps_per_turnover": args.market_impact_bps_per_turnover,
                },
                "grids": {
                    "lookback_bars": _parse_int_grid(args.lookback_bars_grid),
                    "vol_lookback_bars": _parse_int_grid(args.vol_lookback_bars_grid),
                    "target_volatility": _parse_float_grid(args.target_volatility_grid),
                    "max_gross_leverage": _parse_float_grid(args.max_gross_leverage_grid),
                    "max_position_notional_pct": _parse_float_grid(args.max_position_notional_pct_grid),
                    "max_trade_notional_pct": _parse_float_grid(args.max_trade_notional_pct_grid),
                    "max_daily_drawdown_pct": _parse_float_grid(args.max_daily_drawdown_pct_grid),
                    "max_spread_bps": _parse_float_grid(args.max_spread_bps_grid),
                    "fractional_kelly": _parse_float_grid(args.fractional_kelly_grid),
                    "max_kelly_fraction": _parse_float_grid(args.max_kelly_fraction_grid),
                },
                "mean_reversion": {
                    "entry_zscore": args.mean_reversion_entry_zscore,
                    "exit_zscore": args.mean_reversion_exit_zscore,
                },
                "rank_by": args.rank_by,
                "top_n": args.top_n,
            },
            summary={
                "runs": len(runs),
                "symbols": len(symbols),
                "periods": len(periods),
                "rank_by": args.rank_by,
                "artifact_dir": str(artifact_dir),
            },
        )
        ranked_runs = sorted(
            runs,
            key=lambda run: _rank_research_run(run, args.rank_by),
            reverse=args.rank_by != "max_drawdown",
        )
        print(
            "RESEARCH COMPLETE | "
            f"runs={len(runs)} "
            f"symbols={len(symbols)} "
            f"periods={len(periods)} "
            f"rank_by={args.rank_by}"
        )
        for index, run in enumerate(ranked_runs[: args.top_n], start=1):
            report = run.result.risk_report
            metric_value = _rank_research_run(run, args.rank_by)
            excess_vs_symbol_bh = run.result.cumulative_return - run.symbol_buy_hold_cumulative_return
            excess_vs_market_bh = run.result.cumulative_return - run.market_buy_hold_cumulative_return
            metric_text = f"{metric_value:.4f}"
            if "return" in args.rank_by:
                metric_text = f"{metric_value:.2%}"
            print(
                f"#{index} | "
                f"strategy={run.config.strategy_family} "
                f"period={run.config.period_label} "
                f"symbol={run.config.symbol} "
                f"lookback={run.config.lookback_bars} "
                f"vol_lookback={run.config.vol_lookback_bars} "
                f"target_vol={run.config.target_volatility:.3f} "
                f"kelly={run.config.fractional_kelly:.3f} "
                f"cum_return={run.result.cumulative_return:.2%} "
                f"vs_symbol_bh={excess_vs_symbol_bh:.2%} "
                f"vs_market_bh={excess_vs_market_bh:.2%} "
                f"sharpe={report.sharpe_ratio:.3f} "
                f"mdd={report.max_drawdown:.3%} "
                f"{args.rank_by}={metric_text}"
            )
        print(f"ARTIFACTS SAVED | path={artifact_dir}")
        return


def _build_strategy(args, periods_per_year: int) -> StrategyProtocol:
    return build_strategy(
        strategy_family=args.strategy_family,
        symbol=args.symbol,
        lookback_bars=args.lookback_bars,
        vol_lookback_bars=args.vol_lookback_bars,
        target_volatility=args.target_volatility,
        max_gross_leverage=args.max_gross_leverage,
        periods_per_year=periods_per_year,
        allow_short=args.allow_short,
        mean_reversion_entry_zscore=args.mean_reversion_entry_zscore,
        mean_reversion_exit_zscore=args.mean_reversion_exit_zscore,
    )


def _periods_per_year_for_freq(freq: str) -> int:
    mapping = {
        "minute": int(252 * 6.5 * 60),
        "hour": int(252 * 6.5),
        "day": 252,
        "week": 52,
        "month": 12,
    }
    return mapping[freq]


def _add_shared_strategy_and_risk_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lookback-bars",
        type=int,
        default=30,
        help="Number of bars used for momentum estimation",
    )
    parser.add_argument(
        "--vol-lookback-bars",
        type=int,
        default=20,
        help="Number of bars used for realized volatility estimation",
    )
    parser.add_argument(
        "--target-volatility",
        type=float,
        default=0.20,
        help="Annualized target volatility used for vol scaling",
    )
    parser.add_argument(
        "--max-gross-leverage",
        type=float,
        default=1.0,
        help="Hard cap on leverage or exposure multiple",
    )
    parser.add_argument(
        "--max-position-notional-pct",
        type=float,
        default=0.20,
        help="Maximum position size as a fraction of equity",
    )
    parser.add_argument(
        "--max-trade-notional-pct",
        type=float,
        default=0.10,
        help="Maximum single trade notional as a fraction of equity",
    )
    parser.add_argument(
        "--max-daily-drawdown-pct",
        type=float,
        default=0.03,
        help="Daily session drawdown threshold that triggers flattening",
    )
    parser.add_argument(
        "--max-spread-bps",
        type=float,
        default=20.0,
        help="Spread filter in basis points",
    )
    parser.add_argument(
        "--fractional-kelly",
        type=float,
        default=0.25,
        help="Fraction applied to the Kelly estimate",
    )
    parser.add_argument(
        "--max-kelly-fraction",
        type=float,
        default=0.50,
        help="Upper cap on Kelly-based exposure fraction",
    )
    parser.add_argument(
        "--allow-short",
        action="store_true",
        help="Allow short exposure when the momentum signal is negative",
    )
    parser.add_argument(
        "--mean-reversion-entry-zscore",
        type=float,
        default=1.0,
        help="Z-score threshold for entering mean-reversion trades",
    )
    parser.add_argument(
        "--mean-reversion-exit-zscore",
        type=float,
        default=0.25,
        help="Z-score threshold for exiting mean-reversion trades",
    )


def _default_backtest_output_dir(symbol: str, start: str, end: str, freq: str) -> Path:
    safe_symbol = symbol.replace("/", "_").replace("\\", "_")
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "backtests" / f"{safe_symbol}_{freq}_{start}_{end}_{stamp}"


def _default_research_output_dir(periods: list[ResearchPeriod], freq: str) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if len(periods) == 1:
        period = periods[0]
        return Path("artifacts") / "research" / f"{freq}_{period.start}_{period.end}_{stamp}"
    return Path("artifacts") / "research" / f"{freq}_multi_period_{len(periods)}_{stamp}"


def _parse_int_grid(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _parse_float_grid(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def _parse_str_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_periods_arg(raw: str) -> list[ResearchPeriod]:
    periods: list[ResearchPeriod] = []
    for item in raw.split(","):
        entry = item.strip()
        if not entry:
            continue
        start, end = entry.split(":", maxsplit=1)
        start = start.strip()
        end = end.strip()
        periods.append(ResearchPeriod(start=start, end=end, label=f"{start}_to_{end}"))
    if not periods:
        raise ValueError("At least one valid period must be provided.")
    return periods


def _rank_metric(result, rank_by: str) -> float:
    if hasattr(result.risk_report, rank_by):
        return float(getattr(result.risk_report, rank_by))
    if hasattr(result, rank_by):
        return float(getattr(result, rank_by))
    raise ValueError(f"Unsupported rank metric: {rank_by}")


def _rank_research_run(run, rank_by: str) -> float:
    if rank_by == "excess_return_vs_symbol_buy_hold":
        return float(run.result.cumulative_return - run.symbol_buy_hold_cumulative_return)
    if rank_by == "excess_return_vs_market_buy_hold":
        return float(run.result.cumulative_return - run.market_buy_hold_cumulative_return)
    if rank_by == "excess_sharpe_vs_symbol_buy_hold":
        return float(run.result.risk_report.sharpe_ratio - run.symbol_buy_hold_report.sharpe_ratio)
    if rank_by == "excess_sharpe_vs_market_buy_hold":
        return float(run.result.risk_report.sharpe_ratio - run.market_buy_hold_report.sharpe_ratio)
    return _rank_metric(run.result, rank_by)


if __name__ == "__main__":
    main()
