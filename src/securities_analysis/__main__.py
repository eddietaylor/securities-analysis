from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

from securities_analysis.backtest.costs import ExecutionCostModel
from securities_analysis.backtest.engine import StrategyBacktester
from securities_analysis.backtest.reporting import save_backtest_artifacts
from securities_analysis.backtest.research import ResearchPeriod, save_research_artifacts
from securities_analysis.backtest.research import run_research_grid, run_research_periods
from securities_analysis.config import load_alpaca_settings
from securities_analysis.dashboard import (
    build_backtest_dashboard,
    build_forecast_dashboard,
    build_registry_dashboard_index,
)
from securities_analysis.experiments import new_run_id, write_run_manifest
from securities_analysis.execution.alpaca import AlpacaTrader
from securities_analysis.execution.history import build_history_provider
from securities_analysis.forecastability_scan import (
    default_forecastability_output_dir,
    save_forecastability_scan,
    scan_forecastability,
)
from securities_analysis.panel import (
    build_panel_dataset,
    default_panel_metadata,
    default_panel_output_dir,
    default_panel_symbols,
    preset_metadata,
    preset_names,
    preset_symbols,
    save_panel_dataset,
)
from securities_analysis.panel_forecast import (
    PanelForecastConfig,
    default_panel_forecast_output_dir,
    evaluate_global_panel_forecast,
    load_panel_dataset,
    save_panel_forecast_artifacts,
)
from securities_analysis.panel_backtest import (
    PanelBacktestConfig,
    default_panel_backtest_output_dir,
    evaluate_panel_prediction_backtest,
    load_market_benchmark_frame,
    load_panel_predictions,
    save_panel_backtest_artifacts,
)
from securities_analysis.portfolio_blend import (
    default_portfolio_blend_output_dir,
    evaluate_portfolio_blends,
    load_backtest_steps_frame,
    save_portfolio_blend_artifacts,
)
from securities_analysis.runtime import risk_spec_from_args, runtime_spec_from_args
from securities_analysis.runtime import strategy_spec_from_args
from securities_analysis.shortlist_research import (
    default_shortlist_research_output_dir,
    run_shortlist_research,
)
from securities_analysis.services.mvp_execution import MvpExecutionService
from securities_analysis.services.paper_trading import PaperTradingService
from securities_analysis.strategies import StrategyProtocol, build_strategy
from securities_analysis.strategies.forecast_features import (
    forecast_feature_families,
    forecast_feature_presets,
)


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
        choices=["trend", "mean_reversion", "multi_horizon_trend", "feature_linear_forecast", "feature_boosted_forecast", "regime_timing_linear_forecast"],
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
        choices=["trend", "mean_reversion", "multi_horizon_trend", "feature_linear_forecast", "feature_boosted_forecast", "regime_timing_linear_forecast"],
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
    backtest_parser.add_argument(
        "--market-benchmark-symbol",
        default="SPY",
        help="External market benchmark to compare against regardless of traded symbol, e.g. SPY or VOO.",
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
        default="trend,mean_reversion,multi_horizon_trend,feature_linear_forecast,feature_boosted_forecast,regime_timing_linear_forecast",
        help="Comma-separated strategy families to compare, e.g. trend,mean_reversion,multi_horizon_trend,feature_linear_forecast,feature_boosted_forecast,regime_timing_linear_forecast",
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

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Generate static HTML dashboards for backtests and the run explorer index",
    )
    dashboard_parser.add_argument(
        "--artifact-dir",
        help="Optional specific backtest artifact directory to render",
    )
    dashboard_parser.add_argument(
        "--output-path",
        help="Optional output path for a specific dashboard or the explorer index",
    )
    dashboard_parser.add_argument(
        "--registry-path",
        default=str(Path("artifacts") / "registry" / "run_registry.jsonl"),
        help="Path to the run registry JSONL file",
    )
    dashboard_parser.add_argument(
        "--backtests-only",
        action="store_true",
        help="Restrict the explorer index to backtest runs",
    )

    panel_parser = subparsers.add_parser(
        "panel-dataset",
        help="Build a panel-style forecasting dataset across a curated symbol universe",
    )
    panel_parser.add_argument(
        "--symbols",
        default=",".join(default_panel_symbols()),
        help="Comma-separated symbols for the panel dataset",
    )
    panel_parser.add_argument(
        "--universe-preset",
        choices=preset_names(),
        help="Optional named universe preset. If provided, it overrides --symbols and implies the matching asset-class default.",
    )
    panel_parser.add_argument(
        "--asset-class",
        default="equity",
        choices=["equity", "crypto", "future"],
        help="Asset class for all symbols in the panel dataset",
    )
    panel_parser.add_argument("--start", required=True, help="Historical start date YYYY-MM-DD")
    panel_parser.add_argument("--end", required=True, help="Historical end date YYYY-MM-DD")
    panel_parser.add_argument(
        "--freq",
        default="day",
        choices=["minute", "hour", "day", "week", "month"],
        help="Historical bar frequency",
    )
    panel_parser.add_argument(
        "--lookback-bars",
        type=int,
        default=60,
        help="Primary lookback used in feature construction",
    )
    panel_parser.add_argument(
        "--vol-lookback-bars",
        type=int,
        default=20,
        help="Volatility lookback used in feature construction",
    )
    panel_parser.add_argument(
        "--horizons",
        default="5,10,20,60",
        help="Comma-separated forecast horizons in bars",
    )
    panel_parser.add_argument(
        "--output-dir",
        help="Optional output directory for saved panel dataset artifacts",
    )
    panel_parser.add_argument(
        "--history-provider",
        default="alpaca",
        choices=["alpaca", "yfinance"],
        help="Historical market data provider for the panel dataset. Use yfinance for deeper equity/ETF history.",
    )
    panel_parser.add_argument(
        "--feature-preset",
        choices=sorted(forecast_feature_presets()),
        help="Optional forecast feature preset, e.g. momentum_core or mean_reversion_core.",
    )
    panel_parser.add_argument(
        "--feature-families",
        help=(
            "Optional comma-separated forecast feature families to include. "
            f"Available: {','.join(sorted(forecast_feature_families()))}"
        ),
    )
    panel_parser.add_argument(
        "--enhanced-context-features",
        action="store_true",
        help="Enable the richer experimental cross-asset context layer. Off by default for benchmark stability.",
    )

    panel_forecast_parser = subparsers.add_parser(
        "panel-forecast",
        help="Train and evaluate a first global panel forecasting baseline from a saved panel dataset",
    )
    panel_forecast_parser.add_argument(
        "--dataset-dir",
        required=True,
        help="Path to a panel dataset artifact directory containing panel_dataset.csv",
    )
    panel_forecast_parser.add_argument(
        "--horizons",
        default="5,10,20,60",
        help="Comma-separated horizons to model from the panel dataset",
    )
    panel_forecast_parser.add_argument(
        "--model-family",
        default="gradient_boosting",
        choices=["gradient_boosting", "linear_ridge", "catboost"],
        help="Panel forecasting model family to use for the shared multivariate forecast.",
    )
    panel_forecast_parser.add_argument(
        "--min-train-dates",
        type=int,
        default=80,
        help="Minimum number of unique dates before evaluation begins",
    )
    panel_forecast_parser.add_argument(
        "--max-train-dates",
        type=int,
        default=0,
        help="Maximum trailing unique dates to retain for training. Use 0 for expanding history.",
    )
    panel_forecast_parser.add_argument(
        "--retrain-every-dates",
        type=int,
        default=5,
        help="Refit cadence in unique dates",
    )
    panel_forecast_parser.add_argument(
        "--n-estimators",
        type=int,
        default=60,
        help="Number of boosting stages",
    )
    panel_forecast_parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.05,
        help="Boosting learning rate",
    )
    panel_forecast_parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Tree depth for the global boosted model",
    )
    panel_forecast_parser.add_argument(
        "--ridge-alpha",
        type=float,
        default=1.0,
        help="Regularization strength for the linear ridge panel model.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-iterations",
        type=int,
        default=600,
        help="Maximum boosting iterations for CatBoost.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-depth",
        type=int,
        default=6,
        help="Tree depth for CatBoost.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-l2-leaf-reg",
        type=float,
        default=3.0,
        help="L2 leaf regularization for CatBoost.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-random-strength",
        type=float,
        default=1.0,
        help="Random strength for CatBoost score regularization.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-bagging-temperature",
        type=float,
        default=1.0,
        help="Bagging temperature for CatBoost Bayesian bootstrap.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-early-stopping-rounds",
        type=int,
        default=50,
        help="Early stopping rounds for CatBoost.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-validation-fraction",
        type=float,
        default=0.15,
        help="Fraction of each training window reserved as the CatBoost validation slice.",
    )
    panel_forecast_parser.add_argument(
        "--catboost-thread-count",
        type=int,
        default=-1,
        help="Thread count for CatBoost. Use 1 for more reproducible benchmark runs.",
    )
    panel_forecast_parser.add_argument(
        "--include-symbol-identity",
        action="store_true",
        help="Include target symbol identity as a categorical input. Off by default so the model leans on multivariate covariates first.",
    )
    panel_forecast_parser.add_argument(
        "--exclude-bucket-metadata",
        action="store_true",
        help="Exclude asset/bucket metadata categorical inputs.",
    )
    panel_forecast_parser.add_argument(
        "--output-dir",
        help="Optional output directory for saved panel forecast artifacts",
    )

    panel_backtest_parser = subparsers.add_parser(
        "panel-backtest",
        help="Backtest a portfolio built from saved panel forecast predictions",
    )
    panel_backtest_parser.add_argument(
        "--forecast-dir",
        required=True,
        help="Path to a panel forecast artifact directory containing panel_predictions.csv",
    )
    panel_backtest_parser.add_argument(
        "--horizon",
        type=int,
        required=True,
        help="Forecast horizon column to trade, e.g. 120 uses panel_pred_h120.",
    )
    panel_backtest_parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="How many top forecasts to hold on each rebalance date.",
    )
    panel_backtest_parser.add_argument(
        "--rebalance-every-dates",
        type=int,
        default=5,
        help="Rebalance cadence in unique dates.",
    )
    panel_backtest_parser.add_argument(
        "--initial-equity",
        type=float,
        default=100000.0,
        help="Starting equity for the panel portfolio backtest.",
    )
    panel_backtest_parser.add_argument(
        "--target-gross-leverage",
        type=float,
        default=1.0,
        help="Total gross exposure assigned across active positions.",
    )
    panel_backtest_parser.add_argument(
        "--long-threshold",
        type=float,
        default=0.0,
        help="Minimum forecast needed to enter a long position.",
    )
    panel_backtest_parser.add_argument(
        "--allow-short",
        action="store_true",
        help="Enable symmetric long-short ranking instead of long-only selection.",
    )
    panel_backtest_parser.add_argument(
        "--periods-per-year",
        type=int,
        default=252,
        help="Annualization factor for portfolio risk metrics.",
    )
    panel_backtest_parser.add_argument(
        "--spread-bps",
        type=float,
        default=0.0,
        help="Synthetic spread applied in the backtest cost model.",
    )
    panel_backtest_parser.add_argument(
        "--commission-bps",
        type=float,
        default=0.0,
        help="Commission bps in the backtest cost model.",
    )
    panel_backtest_parser.add_argument(
        "--slippage-bps",
        type=float,
        default=2.0,
        help="Slippage bps in the backtest cost model.",
    )
    panel_backtest_parser.add_argument(
        "--market-impact-bps-per-turnover",
        type=float,
        default=5.0,
        help="Impact bps charged per unit of turnover.",
    )
    panel_backtest_parser.add_argument(
        "--output-dir",
        help="Optional output directory for saved panel backtest artifacts",
    )
    panel_backtest_parser.add_argument(
        "--market-benchmark-symbol",
        default="SPY",
        help="External market benchmark to compare against regardless of traded universe, e.g. SPY or VOO.",
    )

    blend_parser = subparsers.add_parser(
        "portfolio-blend",
        help="Evaluate how a sleeve backtest behaves when blended with the market benchmark return stream",
    )
    blend_parser.add_argument(
        "--artifact-dir",
        required=True,
        help="Backtest artifact directory containing steps.csv with market benchmark cumulative returns.",
    )
    blend_parser.add_argument(
        "--sleeve-weights",
        default="0,0.1,0.2,0.3,0.4,0.5",
        help="Comma-separated sleeve weights to evaluate against the market benchmark.",
    )
    blend_parser.add_argument(
        "--periods-per-year",
        type=int,
        default=252,
        help="Annualization factor for portfolio risk metrics.",
    )
    blend_parser.add_argument(
        "--output-dir",
        help="Optional output directory for saved blend analysis artifacts",
    )

    forecastability_parser = subparsers.add_parser(
        "forecastability-scan",
        help="Rank a symbol universe on high-level forecastability diagnostics without fitting forecasting models",
    )
    forecastability_parser.add_argument(
        "--symbols",
        default=",".join(default_panel_symbols()),
        help="Comma-separated symbols for the scan",
    )
    forecastability_parser.add_argument(
        "--universe-preset",
        choices=preset_names(),
        help="Optional named universe preset. If provided, it overrides --symbols and implies the matching asset-class default.",
    )
    forecastability_parser.add_argument(
        "--asset-class",
        default="equity",
        choices=["equity", "crypto", "future"],
        help="Asset class for all symbols in the scan",
    )
    forecastability_parser.add_argument("--start", required=True, help="Historical start date YYYY-MM-DD")
    forecastability_parser.add_argument("--end", required=True, help="Historical end date YYYY-MM-DD")
    forecastability_parser.add_argument(
        "--freq",
        default="day",
        choices=["minute", "hour", "day", "week", "month"],
        help="Historical bar frequency",
    )
    forecastability_parser.add_argument(
        "--history-provider",
        default="yfinance",
        choices=["alpaca", "yfinance"],
        help="Historical market data provider for the scan.",
    )
    forecastability_parser.add_argument(
        "--output-dir",
        help="Optional output directory for saved scan artifacts",
    )
    forecastability_parser.add_argument(
        "--objective",
        default="momentum",
        choices=["momentum", "mean_reversion"],
        help="Ranking objective for the structural scan.",
    )

    shortlist_parser = subparsers.add_parser(
        "shortlist-research",
        help="Run the research funnel: forecastability scan, shortlist selection, then dataset/model evaluation on the shortlist",
    )
    shortlist_parser.add_argument(
        "--universe-preset",
        required=True,
        choices=preset_names(),
        help="Named universe preset to scan first.",
    )
    shortlist_parser.add_argument(
        "--history-provider",
        default="yfinance",
        choices=["alpaca", "yfinance"],
        help="Historical market data provider for the shortlist workflow.",
    )
    shortlist_parser.add_argument("--start", required=True, help="Historical start date YYYY-MM-DD")
    shortlist_parser.add_argument("--end", required=True, help="Historical end date YYYY-MM-DD")
    shortlist_parser.add_argument(
        "--freq",
        default="day",
        choices=["minute", "hour", "day", "week", "month"],
        help="Historical bar frequency",
    )
    shortlist_parser.add_argument(
        "--top-n",
        type=int,
        default=8,
        help="How many top scan symbols to keep before adding any required include-symbols.",
    )
    shortlist_parser.add_argument(
        "--include-symbols",
        default="",
        help="Comma-separated extra symbols to force into the shortlist even if not top-ranked by the scan.",
    )
    shortlist_parser.add_argument(
        "--lookback-bars",
        type=int,
        default=60,
        help="Primary lookback used in feature construction",
    )
    shortlist_parser.add_argument(
        "--vol-lookback-bars",
        type=int,
        default=20,
        help="Volatility lookback used in feature construction",
    )
    shortlist_parser.add_argument(
        "--horizons",
        default="30,45,120",
        help="Comma-separated forecast horizons for the shortlist model run",
    )
    shortlist_parser.add_argument(
        "--model-family",
        default="linear_ridge",
        choices=["gradient_boosting", "linear_ridge", "catboost"],
        help="Model family for the shortlist panel forecast stage.",
    )
    shortlist_parser.add_argument(
        "--min-train-dates",
        type=int,
        default=252,
        help="Minimum number of unique dates before evaluation begins",
    )
    shortlist_parser.add_argument(
        "--max-train-dates",
        type=int,
        default=0,
        help="Maximum trailing unique dates to retain for training. Use 0 for expanding history.",
    )
    shortlist_parser.add_argument(
        "--retrain-every-dates",
        type=int,
        default=126,
        help="Refit cadence in unique dates",
    )
    shortlist_parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.03,
        help="Boosting learning rate",
    )
    shortlist_parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Tree depth for sklearn gradient boosting",
    )
    shortlist_parser.add_argument(
        "--ridge-alpha",
        type=float,
        default=1.0,
        help="Regularization strength for the linear ridge panel model.",
    )
    shortlist_parser.add_argument(
        "--catboost-iterations",
        type=int,
        default=1000,
        help="Maximum boosting iterations for CatBoost.",
    )
    shortlist_parser.add_argument(
        "--catboost-depth",
        type=int,
        default=6,
        help="Tree depth for CatBoost.",
    )
    shortlist_parser.add_argument(
        "--catboost-l2-leaf-reg",
        type=float,
        default=3.0,
        help="L2 leaf regularization for CatBoost.",
    )
    shortlist_parser.add_argument(
        "--catboost-random-strength",
        type=float,
        default=1.0,
        help="Random strength for CatBoost score regularization.",
    )
    shortlist_parser.add_argument(
        "--catboost-bagging-temperature",
        type=float,
        default=1.0,
        help="Bagging temperature for CatBoost Bayesian bootstrap.",
    )
    shortlist_parser.add_argument(
        "--catboost-early-stopping-rounds",
        type=int,
        default=50,
        help="Early stopping rounds for CatBoost.",
    )
    shortlist_parser.add_argument(
        "--catboost-validation-fraction",
        type=float,
        default=0.15,
        help="Fraction of each training window reserved as the CatBoost validation slice.",
    )
    shortlist_parser.add_argument(
        "--catboost-thread-count",
        type=int,
        default=-1,
        help="Thread count for CatBoost. Use 1 for more reproducible benchmark runs.",
    )
    shortlist_parser.add_argument(
        "--include-symbol-identity",
        action="store_true",
        help="Include target symbol identity as a categorical input.",
    )
    shortlist_parser.add_argument(
        "--exclude-bucket-metadata",
        action="store_true",
        help="Exclude asset/bucket metadata categorical inputs.",
    )
    shortlist_parser.add_argument(
        "--output-dir",
        help="Optional output directory for saved shortlist research artifacts",
    )
    shortlist_parser.add_argument(
        "--feature-preset",
        choices=sorted(forecast_feature_presets()),
        help="Optional forecast feature preset used when building the shortlisted panel dataset.",
    )
    shortlist_parser.add_argument(
        "--feature-families",
        help=(
            "Optional comma-separated forecast feature families to include in the shortlisted panel dataset. "
            f"Available: {','.join(sorted(forecast_feature_families()))}"
        ),
    )
    shortlist_parser.add_argument(
        "--enhanced-context-features",
        action="store_true",
        help="Enable the richer experimental cross-asset context layer. Off by default for benchmark stability.",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "account":
        settings = load_alpaca_settings(cfg_path=args.cfg)
        trader = AlpacaTrader(settings)
        account = trader.get_account_details()
        print(account)
        return

    if args.command == "stream":
        settings = load_alpaca_settings(cfg_path=args.cfg)
        trader = AlpacaTrader(settings)
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
        settings = load_alpaca_settings(cfg_path=args.cfg)
        trader = AlpacaTrader(settings)
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
        settings = load_alpaca_settings(cfg_path=args.cfg)
        trader = AlpacaTrader(settings)
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
        if args.market_benchmark_symbol:
            try:
                market_benchmark_bars = trader.get_historical_bar_objects(
                    ticker=args.market_benchmark_symbol,
                    start=args.start,
                    end=args.end,
                    freq=args.freq,
                    asset_class="equity",
                )
                market_benchmark_cumulative_returns = _benchmark_cumulative_returns_for_steps(
                    market_benchmark_bars,
                    result.steps,
                )
                for step, market_cum_return in zip(result.steps, market_benchmark_cumulative_returns):
                    step.signal_metadata["market_buy_hold_cumulative_return"] = float(market_cum_return)
            except Exception:
                pass
        report = result.risk_report
        run_id = new_run_id("backtest")
        metadata = {
            "run_id": run_id,
            "runtime_spec": {
                "strategy": strategy_spec.to_dict(),
                "risk": risk_spec.to_dict(),
            },
            "market_benchmark_symbol": args.market_benchmark_symbol,
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
        settings = load_alpaca_settings(cfg_path=args.cfg)
        trader = AlpacaTrader(settings)
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

    if args.command == "dashboard":
        if args.artifact_dir:
            output_path = build_backtest_dashboard(
                args.artifact_dir,
                output_path=args.output_path,
            )
            forecast_output_path = build_forecast_dashboard(args.artifact_dir)
            print(f"DASHBOARD GENERATED | path={output_path}")
            print(f"FORECAST DASHBOARD GENERATED | path={forecast_output_path}")
            return

        kinds = {"backtest"} if args.backtests_only else None
        output_path = build_registry_dashboard_index(
            registry_path=args.registry_path,
            output_path=args.output_path or Path("artifacts") / "dashboard" / "index.html",
            kinds=kinds,
        )
        print(f"RUN EXPLORER GENERATED | path={output_path}")
        return

    if args.command == "panel-dataset":
        if args.universe_preset:
            symbols = preset_symbols(args.universe_preset)
            metadata_map = preset_metadata(args.universe_preset)
            inferred_asset_class = next(iter(metadata_map.values())).asset_class if metadata_map else args.asset_class
            asset_class = inferred_asset_class
        else:
            symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
            metadata_map = default_panel_metadata()
            asset_class = args.asset_class
        if asset_class == "future" and args.history_provider != "yfinance":
            parser.error("Futures panel datasets currently require --history-provider yfinance.")
        trader = None
        if args.history_provider == "alpaca":
            settings = load_alpaca_settings(cfg_path=args.cfg)
            trader = AlpacaTrader(settings)
        history_provider = build_history_provider(
            history_provider=args.history_provider,
            trader=trader,
        )
        periods_per_year = _periods_per_year_for_freq(args.freq)
        frame = build_panel_dataset(
            history_provider=history_provider,
            symbols=symbols,
            asset_class=asset_class,
            start=args.start,
            end=args.end,
            freq=args.freq,
            lookback_bars=args.lookback_bars,
            vol_lookback_bars=args.vol_lookback_bars,
            horizons=_parse_int_grid(args.horizons),
            periods_per_year=periods_per_year,
            metadata_map=metadata_map,
            feature_families=_parse_str_list(args.feature_families) if args.feature_families else None,
            feature_preset=args.feature_preset,
            enhanced_context_features=args.enhanced_context_features,
        )
        artifact_dir = save_panel_dataset(
            frame,
            output_dir=args.output_dir or default_panel_output_dir(freq=args.freq),
            config={
                "symbols": symbols,
                "asset_class": asset_class,
                "universe_preset": args.universe_preset or "",
                "start": args.start,
                "end": args.end,
                "freq": args.freq,
                "history_provider": args.history_provider,
                "lookback_bars": args.lookback_bars,
                "vol_lookback_bars": args.vol_lookback_bars,
                "horizons": _parse_int_grid(args.horizons),
                "feature_families": _parse_str_list(args.feature_families) if args.feature_families else [],
                "feature_preset": args.feature_preset or "",
                "enhanced_context_features": args.enhanced_context_features,
            },
        )
        print(
            "PANEL DATASET BUILT | "
            f"rows={len(frame)} "
            f"symbols={frame['symbol'].nunique() if not frame.empty else 0} "
            f"path={artifact_dir}"
        )
        return

    if args.command == "panel-forecast":
        panel_frame = load_panel_dataset(args.dataset_dir)
        predictions_frame, overall_metrics, symbol_metrics, summary = evaluate_global_panel_forecast(
            panel_frame,
            config=PanelForecastConfig(
                horizons=_parse_int_grid(args.horizons),
                model_family=args.model_family,
                min_train_dates=args.min_train_dates,
                max_train_dates=(args.max_train_dates if args.max_train_dates and args.max_train_dates > 0 else None),
                retrain_every_dates=args.retrain_every_dates,
                n_estimators=args.n_estimators,
                learning_rate=args.learning_rate,
                max_depth=args.max_depth,
                ridge_alpha=args.ridge_alpha,
                catboost_iterations=args.catboost_iterations,
                catboost_depth=args.catboost_depth,
                catboost_l2_leaf_reg=args.catboost_l2_leaf_reg,
                catboost_random_strength=args.catboost_random_strength,
                catboost_bagging_temperature=args.catboost_bagging_temperature,
                catboost_early_stopping_rounds=args.catboost_early_stopping_rounds,
                catboost_validation_fraction=args.catboost_validation_fraction,
                catboost_thread_count=args.catboost_thread_count,
                include_symbol_identity=args.include_symbol_identity,
                include_bucket_metadata=not args.exclude_bucket_metadata,
            ),
        )
        artifact_dir = save_panel_forecast_artifacts(
            predictions_frame,
            overall_metrics,
            symbol_metrics,
            summary,
            output_dir=args.output_dir or default_panel_forecast_output_dir(),
        )
        print(
            "PANEL FORECAST COMPLETE | "
            f"rows={len(predictions_frame)} "
            f"symbols={predictions_frame['symbol'].nunique() if not predictions_frame.empty else 0} "
            f"path={artifact_dir}"
        )
        return

    if args.command == "forecastability-scan":
        if args.universe_preset:
            symbols = preset_symbols(args.universe_preset)
            metadata_map = preset_metadata(args.universe_preset)
            inferred_asset_class = next(iter(metadata_map.values())).asset_class if metadata_map else args.asset_class
            asset_class = inferred_asset_class
        else:
            symbols = [symbol.strip() for symbol in args.symbols.split(",") if symbol.strip()]
            metadata_map = default_panel_metadata()
            asset_class = args.asset_class
        if asset_class == "future" and args.history_provider != "yfinance":
            parser.error("Futures forecastability scans currently require --history-provider yfinance.")
        trader = None
        if args.history_provider == "alpaca":
            settings = load_alpaca_settings(cfg_path=args.cfg)
            trader = AlpacaTrader(settings)
        history_provider = build_history_provider(
            history_provider=args.history_provider,
            trader=trader,
        )
        universe = [metadata_map[symbol] for symbol in symbols if symbol in metadata_map]
        frame = scan_forecastability(
            history_provider=history_provider,
            universe=universe,
            start=args.start,
            end=args.end,
            freq=args.freq,
            objective=args.objective,
        )
        artifact_dir = save_forecastability_scan(
            frame,
            output_dir=args.output_dir or default_forecastability_output_dir(),
            config={
                "symbols": symbols,
                "asset_class": asset_class,
                "universe_preset": args.universe_preset or "",
                "start": args.start,
                "end": args.end,
                "freq": args.freq,
                "history_provider": args.history_provider,
                "objective": args.objective,
            },
        )
        print(
            "FORECASTABILITY SCAN COMPLETE | "
            f"rows={len(frame)} "
            f"path={artifact_dir}"
        )
        return

    if args.command == "shortlist-research":
        metadata_map = preset_metadata(args.universe_preset)
        asset_class = next(iter(metadata_map.values())).asset_class if metadata_map else "future"
        if asset_class == "future" and args.history_provider != "yfinance":
            parser.error("Futures shortlist research currently requires --history-provider yfinance.")
        trader = None
        if args.history_provider == "alpaca":
            settings = load_alpaca_settings(cfg_path=args.cfg)
            trader = AlpacaTrader(settings)
        history_provider = build_history_provider(
            history_provider=args.history_provider,
            trader=trader,
        )
        periods_per_year = _periods_per_year_for_freq(args.freq)
        include_symbols = _parse_str_list(args.include_symbols) if args.include_symbols else []
        result = run_shortlist_research(
            history_provider=history_provider,
            universe=list(metadata_map.values()),
            start=args.start,
            end=args.end,
            freq=args.freq,
            top_n=args.top_n,
            include_symbols=include_symbols,
            lookback_bars=args.lookback_bars,
            vol_lookback_bars=args.vol_lookback_bars,
            horizons=_parse_int_grid(args.horizons),
            periods_per_year=periods_per_year,
            model_config=PanelForecastConfig(
                horizons=_parse_int_grid(args.horizons),
                model_family=args.model_family,
                min_train_dates=args.min_train_dates,
                max_train_dates=(args.max_train_dates if args.max_train_dates and args.max_train_dates > 0 else None),
                retrain_every_dates=args.retrain_every_dates,
                learning_rate=args.learning_rate,
                max_depth=args.max_depth,
                ridge_alpha=args.ridge_alpha,
                catboost_iterations=args.catboost_iterations,
                catboost_depth=args.catboost_depth,
                catboost_l2_leaf_reg=args.catboost_l2_leaf_reg,
                catboost_random_strength=args.catboost_random_strength,
                catboost_bagging_temperature=args.catboost_bagging_temperature,
                catboost_early_stopping_rounds=args.catboost_early_stopping_rounds,
                catboost_validation_fraction=args.catboost_validation_fraction,
                catboost_thread_count=args.catboost_thread_count,
                include_symbol_identity=args.include_symbol_identity,
                include_bucket_metadata=not args.exclude_bucket_metadata,
            ),
            output_dir=args.output_dir or default_shortlist_research_output_dir(),
            feature_families=_parse_str_list(args.feature_families) if args.feature_families else None,
            feature_preset=args.feature_preset,
            enhanced_context_features=args.enhanced_context_features,
        )
        print(
            "SHORTLIST RESEARCH COMPLETE | "
            f"symbols={','.join(result.shortlist_symbols)} "
            f"path={result.forecast_artifact_dir.parent}"
        )
        return

    if args.command == "panel-backtest":
        predictions_frame = load_panel_predictions(args.forecast_dir)
        market_benchmark_frame = None
        if args.market_benchmark_symbol:
            history_provider = build_history_provider(history_provider="yfinance")
            prediction_dates = sorted(pd.to_datetime(predictions_frame["timestamp"], utc=True).dropna().unique())
            market_benchmark_frame = load_market_benchmark_frame(
                history_provider=history_provider,
                symbol=args.market_benchmark_symbol,
                dates=list(prediction_dates),
                freq="day",
            )
        result = evaluate_panel_prediction_backtest(
            predictions_frame,
            config=PanelBacktestConfig(
                horizon_bars=args.horizon,
                top_k=args.top_k,
                rebalance_every_dates=args.rebalance_every_dates,
                initial_equity=args.initial_equity,
                target_gross_leverage=args.target_gross_leverage,
                long_threshold=args.long_threshold,
                allow_short=args.allow_short,
                spread_bps=args.spread_bps,
                periods_per_year=args.periods_per_year,
                commission_bps=args.commission_bps,
                slippage_bps=args.slippage_bps,
                market_impact_bps_per_turnover=args.market_impact_bps_per_turnover,
                market_benchmark_symbol=args.market_benchmark_symbol,
            ),
            market_benchmark_frame=market_benchmark_frame,
        )
        artifact_dir = save_panel_backtest_artifacts(
            result,
            output_dir=args.output_dir or default_panel_backtest_output_dir(),
            metadata={
                "panel_backtest": {
                    "forecast_dir": args.forecast_dir,
                    "horizon": args.horizon,
                    "top_k": args.top_k,
                    "rebalance_every_dates": args.rebalance_every_dates,
                    "initial_equity": args.initial_equity,
                    "target_gross_leverage": args.target_gross_leverage,
                    "long_threshold": args.long_threshold,
                    "allow_short": args.allow_short,
                    "market_benchmark_symbol": args.market_benchmark_symbol,
                },
                "costs": {
                    "spread_bps": args.spread_bps,
                    "commission_bps": args.commission_bps,
                    "slippage_bps": args.slippage_bps,
                    "market_impact_bps_per_turnover": args.market_impact_bps_per_turnover,
                },
            },
        )
        print(
            "PANEL BACKTEST COMPLETE | "
            f"final_equity={result.final_equity:.2f} "
            f"cumulative_return={result.cumulative_return:.4f} "
            f"path={artifact_dir}"
        )
        return

    if args.command == "portfolio-blend":
        steps_frame = load_backtest_steps_frame(args.artifact_dir)
        result = evaluate_portfolio_blends(
            steps_frame,
            periods_per_year=args.periods_per_year,
            sleeve_weights=_parse_float_grid(args.sleeve_weights),
        )
        artifact_dir = save_portfolio_blend_artifacts(
            result,
            output_dir=args.output_dir or default_portfolio_blend_output_dir(),
        )
        best_sharpe = result.summary.get("best_sharpe_weight", {})
        print(
            "PORTFOLIO BLEND COMPLETE | "
            f"best_sharpe_sleeve_weight={best_sharpe.get('sleeve_weight', float('nan')):.2f} "
            f"path={artifact_dir}"
        )
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
    parser.add_argument(
        "--max-train-samples",
        type=int,
        default=0,
        help="Maximum number of training observations retained by trainable forecast models. Use 0 for expanding history.",
    )


def _default_backtest_output_dir(symbol: str, start: str, end: str, freq: str) -> Path:
    safe_symbol = symbol.replace("/", "_").replace("\\", "_")
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "backtests" / f"{safe_symbol}_{freq}_{start}_{end}_{stamp}"


def _benchmark_cumulative_returns_for_steps(bars: list, steps: list) -> list[float]:
    if not bars or not steps:
        return []
    benchmark_frame = pd.DataFrame(
        {
            "timestamp": [bar.end_time for bar in bars],
            "close_price": [bar.close_price for bar in bars],
        }
    )
    benchmark_frame["timestamp"] = pd.to_datetime(benchmark_frame["timestamp"], utc=True)
    benchmark_frame = benchmark_frame.dropna(subset=["close_price"]).sort_values("timestamp")
    if benchmark_frame.empty:
        return []
    step_times = pd.DatetimeIndex(pd.to_datetime([step.bar.end_time for step in steps], utc=True))
    benchmark_close = pd.Series(
        benchmark_frame["close_price"].astype(float).to_numpy(),
        index=pd.DatetimeIndex(benchmark_frame["timestamp"]),
    )
    aligned_close = benchmark_close.reindex(step_times).ffill().bfill()
    if aligned_close.empty or aligned_close.isna().all():
        return []
    first_close = float(aligned_close.iloc[0])
    return list((aligned_close / max(first_close, 1e-8) - 1.0).astype(float))


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
