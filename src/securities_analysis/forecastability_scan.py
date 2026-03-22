from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from securities_analysis.execution.history import HistoricalPriceProvider
from securities_analysis.forecast_validation import prepare_forecast_validation_frame
from securities_analysis.panel import UniverseSymbol


@dataclass(slots=True)
class ForecastabilityScanResult:
    symbol: str
    asset_class: str
    bucket: str
    sub_bucket: str
    observations: int
    start: str
    end: str
    lag1_autocorrelation: float
    variance_ratio_5: float
    variance_ratio_20: float
    spectral_entropy: float
    momentum_forecastability_score: float


def scan_forecastability(
    *,
    history_provider: HistoricalPriceProvider,
    universe: Iterable[UniverseSymbol],
    start: str,
    end: str,
    freq: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item in universe:
        bars = history_provider.get_historical_prices(
            ticker=item.symbol,
            start=start,
            end=end,
            freq=freq,
            asset_class=item.asset_class,
        )
        result = _scan_single_symbol(
            symbol=item.symbol,
            asset_class=item.asset_class,
            bucket=item.bucket,
            sub_bucket=item.sub_bucket,
            bars=bars,
        )
        if result is not None:
            rows.append(asdict(result))
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame = frame.sort_values(
        ["momentum_forecastability_score", "observations"],
        ascending=[False, False],
    ).reset_index(drop=True)
    frame["rank"] = np.arange(1, len(frame) + 1)
    return frame[
        [
            "rank",
            "symbol",
            "asset_class",
            "bucket",
            "sub_bucket",
            "observations",
            "start",
            "end",
            "lag1_autocorrelation",
            "variance_ratio_5",
            "variance_ratio_20",
            "spectral_entropy",
            "momentum_forecastability_score",
        ]
    ]


def save_forecastability_scan(
    frame: pd.DataFrame,
    *,
    output_dir: str | Path,
    config: dict[str, object],
) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(artifact_dir / "forecastability_scan.csv", index=False)
    summary = {
        "rows": int(len(frame)),
        "config": config,
        "top_symbols": frame.head(10)["symbol"].tolist() if not frame.empty else [],
    }
    (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return artifact_dir


def default_forecastability_output_dir() -> Path:
    stamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "forecastability_scans" / f"scan_{stamp}"


def _scan_single_symbol(
    *,
    symbol: str,
    asset_class: str,
    bucket: str,
    sub_bucket: str,
    bars: pd.DataFrame,
) -> ForecastabilityScanResult | None:
    if bars.empty:
        return None

    frame = bars.reset_index()
    if "timestamp" not in frame.columns or "close" not in frame.columns:
        return None
    frame = frame.replace([np.inf, -np.inf], np.nan)
    frame = frame.dropna(subset=["close"]).copy()
    frame = frame.loc[frame["close"].astype(float) > 0].reset_index(drop=True)
    if len(frame) < 252:
        return None

    steps = frame.rename(columns={"close": "close_price"})[["timestamp", "close_price"]].copy()
    prepared = prepare_forecast_validation_frame(steps)
    returns = prepared["asset_log_return"].dropna().astype(float).to_numpy()
    if returns.size < 50:
        return None

    lag1 = _safe_autocorrelation(returns, 1)
    vr5 = _variance_ratio(returns, 5)
    vr20 = _variance_ratio(returns, 20)
    entropy = _spectral_entropy(returns)
    score = _momentum_forecastability_score(lag1=lag1, vr5=vr5, vr20=vr20, entropy=entropy)
    return ForecastabilityScanResult(
        symbol=symbol,
        asset_class=asset_class,
        bucket=bucket,
        sub_bucket=sub_bucket,
        observations=int(len(frame)),
        start=str(pd.to_datetime(frame["timestamp"]).min()),
        end=str(pd.to_datetime(frame["timestamp"]).max()),
        lag1_autocorrelation=lag1,
        variance_ratio_5=vr5,
        variance_ratio_20=vr20,
        spectral_entropy=entropy,
        momentum_forecastability_score=score,
    )


def _momentum_forecastability_score(
    *,
    lag1: float,
    vr5: float,
    vr20: float,
    entropy: float,
) -> float:
    lag_component = 0.0 if math.isnan(lag1) else max(min(lag1, 0.25), -0.25) / 0.25
    vr5_component = 0.0 if math.isnan(vr5) else max(min(vr5 - 1.0, 1.0), -1.0)
    vr20_component = 0.0 if math.isnan(vr20) else max(min(vr20 - 1.0, 1.0), -1.0)
    entropy_component = 0.0 if math.isnan(entropy) else 1.0 - max(min(entropy, 1.0), 0.0)
    return (
        0.35 * lag_component
        + 0.20 * vr5_component
        + 0.30 * vr20_component
        + 0.15 * entropy_component
    )


def _safe_autocorrelation(values: np.ndarray, lag: int) -> float:
    if values.size <= lag:
        return math.nan
    return float(np.corrcoef(values[lag:], values[:-lag])[0, 1])


def _variance_ratio(returns: np.ndarray, horizon: int) -> float:
    if returns.size <= horizon + 1:
        return math.nan
    one_step_var = float(np.var(returns, ddof=1))
    horizon_returns = np.convolve(returns, np.ones(horizon), mode="valid")
    horizon_var = float(np.var(horizon_returns, ddof=1))
    return horizon_var / max(horizon * one_step_var, 1e-12)


def _spectral_entropy(values: np.ndarray) -> float:
    centered = values - np.mean(values)
    spectrum = np.abs(np.fft.rfft(centered)) ** 2
    spectrum = spectrum[1:] if spectrum.size > 1 else spectrum
    total_power = float(np.sum(spectrum))
    if total_power <= 0:
        return math.nan
    probs = spectrum / total_power
    entropy = -float(np.sum(probs * np.log(probs + 1e-12)))
    max_entropy = math.log(len(probs)) if len(probs) > 1 else 1.0
    return entropy / max(max_entropy, 1e-12)
