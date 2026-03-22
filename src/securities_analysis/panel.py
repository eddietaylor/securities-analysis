from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from securities_analysis.strategies.forecast_features import (
    build_forecast_feature_vector,
    forecast_feature_names,
)


class HistoricalPriceProvider(Protocol):
    def get_historical_prices(
        self,
        ticker: str,
        start: str,
        end: str,
        freq: str = "day",
        asset_class: str | None = None,
    ) -> pd.DataFrame: ...


@dataclass(slots=True)
class UniverseSymbol:
    symbol: str
    asset_class: str
    bucket: str
    sub_bucket: str
    liquidity_bucket: str = "high"


DEFAULT_PANEL_UNIVERSE: tuple[UniverseSymbol, ...] = (
    UniverseSymbol("SPY", "equity", "equity_index", "broad_us"),
    UniverseSymbol("QQQ", "equity", "equity_index", "growth_us"),
    UniverseSymbol("IWM", "equity", "equity_index", "small_cap_us"),
    UniverseSymbol("DIA", "equity", "equity_index", "industrial_large_cap"),
    UniverseSymbol("TLT", "equity", "rates", "long_duration_treasury"),
    UniverseSymbol("IEF", "equity", "rates", "intermediate_treasury"),
    UniverseSymbol("GLD", "equity", "metals", "gold"),
    UniverseSymbol("SLV", "equity", "metals", "silver"),
    UniverseSymbol("XLK", "equity", "sector", "technology"),
    UniverseSymbol("XLF", "equity", "sector", "financials"),
    UniverseSymbol("XLE", "equity", "sector", "energy"),
    UniverseSymbol("XLU", "equity", "sector", "utilities"),
)

MOMENTUM_FIT_MACRO_UNIVERSE: tuple[UniverseSymbol, ...] = (
    UniverseSymbol("GLD", "equity", "momentum_macro", "gold"),
    UniverseSymbol("SLV", "equity", "momentum_macro", "silver"),
    UniverseSymbol("TLT", "equity", "momentum_macro", "long_duration_treasury"),
    UniverseSymbol("IEF", "equity", "momentum_macro", "intermediate_treasury"),
    UniverseSymbol("SPY", "equity", "momentum_control", "broad_us_equity"),
    UniverseSymbol("QQQ", "equity", "momentum_control", "growth_us_equity"),
    UniverseSymbol("IWM", "equity", "momentum_control", "small_cap_us_equity"),
    UniverseSymbol("DIA", "equity", "momentum_control", "industrial_large_cap"),
)

MOMENTUM_FIT_CRYPTO_UNIVERSE: tuple[UniverseSymbol, ...] = (
    UniverseSymbol("BTC/USD", "crypto", "momentum_crypto", "bitcoin"),
    UniverseSymbol("ETH/USD", "crypto", "momentum_crypto", "ethereum"),
    UniverseSymbol("SOL/USD", "crypto", "momentum_crypto", "solana"),
    UniverseSymbol("AVAX/USD", "crypto", "momentum_crypto", "avalanche"),
)

MOMENTUM_FIT_FUTURES_UNIVERSE: tuple[UniverseSymbol, ...] = (
    UniverseSymbol("ES=F", "future", "momentum_futures", "sp500_index_future"),
    UniverseSymbol("NQ=F", "future", "momentum_futures", "nasdaq_index_future"),
    UniverseSymbol("ZN=F", "future", "momentum_futures", "ten_year_treasury_future"),
    UniverseSymbol("ZB=F", "future", "momentum_futures", "thirty_year_treasury_future"),
    UniverseSymbol("GC=F", "future", "momentum_futures", "gold_future"),
    UniverseSymbol("CL=F", "future", "momentum_futures", "crude_oil_future"),
)

FUTURES_BROAD_UNIVERSE: tuple[UniverseSymbol, ...] = (
    UniverseSymbol("ES=F", "future", "equity_index_future", "sp500"),
    UniverseSymbol("NQ=F", "future", "equity_index_future", "nasdaq100"),
    UniverseSymbol("YM=F", "future", "equity_index_future", "dow"),
    UniverseSymbol("RTY=F", "future", "equity_index_future", "russell2000"),
    UniverseSymbol("ZN=F", "future", "rates_future", "us10y"),
    UniverseSymbol("ZB=F", "future", "rates_future", "us30y"),
    UniverseSymbol("ZF=F", "future", "rates_future", "us5y"),
    UniverseSymbol("ZT=F", "future", "rates_future", "us2y"),
    UniverseSymbol("GC=F", "future", "metals_future", "gold"),
    UniverseSymbol("SI=F", "future", "metals_future", "silver"),
    UniverseSymbol("HG=F", "future", "metals_future", "copper"),
    UniverseSymbol("CL=F", "future", "energy_future", "crude_oil"),
    UniverseSymbol("NG=F", "future", "energy_future", "natural_gas"),
    UniverseSymbol("RB=F", "future", "energy_future", "gasoline"),
    UniverseSymbol("HO=F", "future", "energy_future", "heating_oil"),
    UniverseSymbol("ZC=F", "future", "agriculture_future", "corn"),
    UniverseSymbol("ZS=F", "future", "agriculture_future", "soybeans"),
    UniverseSymbol("ZW=F", "future", "agriculture_future", "wheat"),
    UniverseSymbol("KC=F", "future", "agriculture_future", "coffee"),
    UniverseSymbol("CT=F", "future", "agriculture_future", "cotton"),
    UniverseSymbol("6E=F", "future", "fx_future", "eurusd"),
    UniverseSymbol("6J=F", "future", "fx_future", "usdjpy"),
    UniverseSymbol("6B=F", "future", "fx_future", "gbpusd"),
    UniverseSymbol("6A=F", "future", "fx_future", "audusd"),
)

UNIVERSE_PRESETS: dict[str, tuple[UniverseSymbol, ...]] = {
    "panel_default": DEFAULT_PANEL_UNIVERSE,
    "momentum_macro": MOMENTUM_FIT_MACRO_UNIVERSE,
    "momentum_crypto": MOMENTUM_FIT_CRYPTO_UNIVERSE,
    "momentum_futures": MOMENTUM_FIT_FUTURES_UNIVERSE,
    "futures_broad": FUTURES_BROAD_UNIVERSE,
}


def default_panel_symbols() -> list[str]:
    return [item.symbol for item in DEFAULT_PANEL_UNIVERSE]


def default_panel_metadata() -> dict[str, UniverseSymbol]:
    return {item.symbol: item for item in DEFAULT_PANEL_UNIVERSE}


def preset_names() -> list[str]:
    return sorted(UNIVERSE_PRESETS)


def preset_symbols(name: str) -> list[str]:
    if name not in UNIVERSE_PRESETS:
        raise KeyError(f"Unknown universe preset: {name}")
    return [item.symbol for item in UNIVERSE_PRESETS[name]]


def preset_metadata(name: str) -> dict[str, UniverseSymbol]:
    if name not in UNIVERSE_PRESETS:
        raise KeyError(f"Unknown universe preset: {name}")
    return {item.symbol: item for item in UNIVERSE_PRESETS[name]}


def build_panel_dataset(
    *,
    history_provider: HistoricalPriceProvider,
    symbols: list[str],
    asset_class: str,
    start: str,
    end: str,
    freq: str,
    lookback_bars: int,
    vol_lookback_bars: int,
    horizons: list[int],
    periods_per_year: int,
    metadata_map: dict[str, UniverseSymbol] | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    metadata_map = metadata_map or default_panel_metadata()
    feature_names = forecast_feature_names()

    for symbol in symbols:
        bars = history_provider.get_historical_prices(
            ticker=symbol,
            start=start,
            end=end,
            freq=freq,
            asset_class=asset_class,
        )
        symbol_frame = _build_symbol_panel_frame(
            symbol=symbol,
            bars_df=bars,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            horizons=horizons,
            periods_per_year=periods_per_year,
            feature_names=feature_names,
            metadata=metadata_map.get(symbol),
        )
        if not symbol_frame.empty:
            rows.extend(symbol_frame.to_dict(orient="records"))

    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    frame = _add_multivariate_context_features(frame)
    return frame


def save_panel_dataset(
    frame: pd.DataFrame,
    *,
    output_dir: str | Path,
    config: dict[str, object],
) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(artifact_dir / "panel_dataset.csv", index=False)
    summary = {
        "rows": int(len(frame)),
        "symbols": int(frame["symbol"].nunique()) if not frame.empty else 0,
        "start": str(frame["timestamp"].min()) if not frame.empty else "",
        "end": str(frame["timestamp"].max()) if not frame.empty else "",
        "feature_columns": [column for column in frame.columns if column.startswith("feature_")],
        "context_columns": [column for column in frame.columns if column.startswith("context_")],
        "target_columns": [column for column in frame.columns if column.startswith("target_")],
        "config": config,
    }
    (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return artifact_dir


def _build_symbol_panel_frame(
    *,
    symbol: str,
    bars_df: pd.DataFrame,
    lookback_bars: int,
    vol_lookback_bars: int,
    horizons: list[int],
    periods_per_year: int,
    feature_names: list[str],
    metadata: UniverseSymbol | None,
) -> pd.DataFrame:
    if bars_df.empty:
        return pd.DataFrame()

    frame = bars_df.reset_index()
    if "timestamp" not in frame.columns:
        raise KeyError("Historical bars dataframe is missing a timestamp column")
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=["close"]).copy()
    frame = frame.loc[frame["close"].astype(float) > 0].reset_index(drop=True)
    if frame.empty:
        return pd.DataFrame()

    closes = frame["close"].astype(float).to_numpy()
    timestamps = pd.to_datetime(frame["timestamp"]).to_list()
    volumes = frame["volume"].astype(float).to_numpy() if "volume" in frame.columns else np.full(len(frame), np.nan)
    records: list[dict[str, object]] = []
    max_horizon = max(horizons)
    min_index = max(lookback_bars, vol_lookback_bars, 20)

    for idx in range(min_index, len(frame) - max_horizon):
        window_closes = closes[: idx + 1]
        timestamp = timestamps[idx]
        features = build_forecast_feature_vector(
            window_closes,
            periods_per_year=periods_per_year,
            lookback_bars=lookback_bars,
            vol_lookback_bars=vol_lookback_bars,
            timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
        )
        if features is None:
            continue

        row: dict[str, object] = {
            "timestamp": timestamp,
            "symbol": symbol,
            "close_price": float(closes[idx]),
            "volume": float(volumes[idx]) if not np.isnan(volumes[idx]) else None,
        }
        if metadata is not None:
            row["asset_class"] = metadata.asset_class
            row["universe_bucket"] = metadata.bucket
            row["sub_bucket"] = metadata.sub_bucket
            row["liquidity_bucket"] = metadata.liquidity_bucket
        else:
            row["asset_class"] = "equity"
            row["universe_bucket"] = "unknown"
            row["sub_bucket"] = "unknown"
            row["liquidity_bucket"] = "unknown"

        for name, value in zip(feature_names, features, strict=True):
            row[f"feature_{name}"] = float(value)

        for horizon in horizons:
            future_price = float(closes[idx + horizon])
            current_price = float(closes[idx])
            if not np.isfinite(future_price) or not np.isfinite(current_price) or future_price <= 0.0 or current_price <= 0.0:
                continue
            future_return = float(np.log(future_price / current_price))
            if not np.isfinite(future_return):
                continue
            row[f"target_log_return_h{horizon}"] = future_return
            row[f"target_direction_h{horizon}"] = int(np.sign(future_return))

        if all(f"target_log_return_h{horizon}" in row for horizon in horizons):
            records.append(row)

    return pd.DataFrame(records)


def default_panel_output_dir(*, freq: str) -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "panel_datasets" / f"{freq}_{stamp}"


def _add_multivariate_context_features(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame

    working = frame.copy()
    context_source_columns = [
        "feature_ret_5",
        "feature_ret_20",
        "feature_vol_20",
        "feature_drawdown_depth",
    ]

    # Add bucket-level averages excluding the current row where possible.
    for column in context_source_columns:
        bucket_sum = working.groupby(["timestamp", "universe_bucket"])[column].transform("sum")
        bucket_count = working.groupby(["timestamp", "universe_bucket"])[column].transform("count")
        overall_sum = working.groupby("timestamp")[column].transform("sum")
        overall_count = working.groupby("timestamp")[column].transform("count")

        working[f"context_bucket_mean_{column.removeprefix('feature_')}"] = np.where(
            bucket_count > 1,
            (bucket_sum - working[column]) / (bucket_count - 1),
            np.nan,
        )
        working[f"context_market_mean_{column.removeprefix('feature_')}"] = np.where(
            overall_count > 1,
            (overall_sum - working[column]) / (overall_count - 1),
            np.nan,
        )

    # Add reference-symbol context features when those reference instruments exist in the same universe.
    reference_symbols = ["SPY", "QQQ", "TLT", "GLD", "BTC/USD", "ETH/USD"]
    available_reference_symbols = [symbol for symbol in reference_symbols if symbol in set(working["symbol"].unique())]
    for ref_symbol in available_reference_symbols:
        ref_frame = (
            working.loc[working["symbol"] == ref_symbol, ["timestamp", *context_source_columns]]
            .drop_duplicates(subset=["timestamp"])
            .rename(
                columns={
                    column: f"context_{ref_symbol.replace('/', '_')}_{column.removeprefix('feature_')}"
                    for column in context_source_columns
                }
            )
        )
        working = working.merge(ref_frame, on="timestamp", how="left")

    return working
