from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from securities_analysis.backtest.costs import ExecutionCostModel
from securities_analysis.backtest.engine import StrategyBacktester
from securities_analysis.backtest.reporting import save_backtest_artifacts
from securities_analysis.config import load_alpaca_settings
from securities_analysis.execution.alpaca import AlpacaTrader
from securities_analysis.risk.policy import RiskPolicy
from securities_analysis.services.mvp_execution import MvpExecutionService
from securities_analysis.services.paper_trading import PaperTradingService
from securities_analysis.strategies.trend_following import TimeSeriesMomentumStrategy


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
    for parser_obj in (mvp_parser, backtest_parser):
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
        strategy = _build_strategy(args, periods_per_year)
        risk_policy = _build_risk_policy(args, periods_per_year)
        service = MvpExecutionService(
            trader=trader,
            strategy=strategy,
            risk_policy=risk_policy,
            symbol=args.symbol,
            asset_class=args.asset_class,
            interval_seconds=args.interval_seconds,
            dry_run=not args.live_orders,
            warmup_start=args.warmup_start,
            warmup_end=args.warmup_end,
            warmup_freq=args.warmup_freq,
        )
        service.run()
        return

    if args.command == "backtest":
        periods_per_year = _periods_per_year_for_freq(args.freq)
        strategy = _build_strategy(args, periods_per_year)
        risk_policy = _build_risk_policy(args, periods_per_year)
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
        print(
            "BACKTEST RESULT | "
            f"symbol={result.symbol} "
            f"bars={result.bars_processed} "
            f"warmup={result.warmup_bars} "
            f"trades={result.trades} "
            f"final_equity={result.final_equity:.2f} "
            f"cum_return={result.cumulative_return:.2%}"
        )
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
        artifact_dir = save_backtest_artifacts(result, output_dir)
        print(f"ARTIFACTS SAVED | path={artifact_dir}")


def _build_strategy(args, periods_per_year: int) -> TimeSeriesMomentumStrategy:
    return TimeSeriesMomentumStrategy(
        symbol=args.symbol,
        lookback_bars=args.lookback_bars,
        vol_lookback_bars=args.vol_lookback_bars,
        target_volatility=args.target_volatility,
        max_gross_leverage=args.max_gross_leverage,
        periods_per_year=periods_per_year,
        min_bars=max(args.lookback_bars, args.vol_lookback_bars) + 5,
        long_only=not args.allow_short,
    )


def _build_risk_policy(args, periods_per_year: int) -> RiskPolicy:
    return RiskPolicy(
        periods_per_year=periods_per_year,
        max_gross_leverage=args.max_gross_leverage,
        max_position_notional_pct=args.max_position_notional_pct,
        max_trade_notional_pct=args.max_trade_notional_pct,
        max_daily_drawdown_pct=args.max_daily_drawdown_pct,
        max_spread_bps=args.max_spread_bps,
        fractional_kelly=args.fractional_kelly,
        max_kelly_fraction=args.max_kelly_fraction,
        allow_short=args.allow_short,
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


def _default_backtest_output_dir(symbol: str, start: str, end: str, freq: str) -> Path:
    safe_symbol = symbol.replace("/", "_").replace("\\", "_")
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "backtests" / f"{safe_symbol}_{freq}_{start}_{end}_{stamp}"


if __name__ == "__main__":
    main()
