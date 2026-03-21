from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


HORIZON_PATTERN = re.compile(r"^h(?P<horizon>\d+)_expected_return$")


def prepare_forecast_validation_frame(steps_frame: pd.DataFrame) -> pd.DataFrame:
    frame = steps_frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["asset_log_return"] = np.log(frame["close_price"]).diff()
    return frame


def horizon_columns(frame: pd.DataFrame) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for column in frame.columns:
        match = HORIZON_PATTERN.match(column)
        if match:
            mapping[int(match.group("horizon"))] = column
    return dict(sorted(mapping.items()))


def add_realized_horizon_returns(frame: pd.DataFrame) -> pd.DataFrame:
    prepared = frame.copy()
    horizon_map = horizon_columns(prepared)
    log_prices = np.log(prepared["close_price"].astype(float))
    for horizon in horizon_map:
        prepared[f"realized_return_h{horizon}"] = log_prices.shift(-horizon) - log_prices
    return prepared


def compute_forecast_diagnostics(steps_frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = add_realized_horizon_returns(prepare_forecast_validation_frame(steps_frame))
    metrics_rows: list[dict[str, Any]] = []
    horizon_map = horizon_columns(frame)

    for horizon, forecast_column in horizon_map.items():
        realized_column = f"realized_return_h{horizon}"
        sample = frame[[forecast_column, realized_column]].dropna()
        if sample.empty:
            continue

        forecast_values = sample[forecast_column].astype(float).to_numpy()
        realized_values = sample[realized_column].astype(float).to_numpy()
        correlation = float(np.corrcoef(forecast_values, realized_values)[0, 1]) if sample.shape[0] > 1 else math.nan
        mae = float(np.mean(np.abs(forecast_values - realized_values)))
        rmse = float(np.sqrt(np.mean(np.square(forecast_values - realized_values))))
        bias = float(np.mean(forecast_values - realized_values))
        directional_accuracy = float(np.mean(np.sign(forecast_values) == np.sign(realized_values)))
        hit_rate_nonzero = float(
            np.mean(np.sign(forecast_values[np.sign(forecast_values) != 0]) == np.sign(realized_values[np.sign(forecast_values) != 0]))
        ) if np.any(np.sign(forecast_values) != 0) else math.nan

        metrics_rows.append(
            {
                "horizon_bars": horizon,
                "observations": int(sample.shape[0]),
                "forecast_column": forecast_column,
                "correlation": correlation,
                "mae": mae,
                "rmse": rmse,
                "bias": bias,
                "directional_accuracy": directional_accuracy,
                "directional_accuracy_nonzero": hit_rate_nonzero,
                "forecast_mean": float(np.mean(forecast_values)),
                "realized_mean": float(np.mean(realized_values)),
                "forecast_std": float(np.std(forecast_values, ddof=1)) if sample.shape[0] > 1 else math.nan,
                "realized_std": float(np.std(realized_values, ddof=1)) if sample.shape[0] > 1 else math.nan,
            }
        )

    metrics_frame = pd.DataFrame(metrics_rows)
    summary = {
        "validation_method": {
            "name": "rolling_origin_walk_forward",
            "description": (
                "Each forecast at time t is produced using only information available up to time t, "
                "then compared to the realized future return over each horizon. "
                "This is a chronological rolling-origin evaluation, not shuffled k-fold cross-validation."
            ),
            "uses_shuffled_folds": False,
            "retrain_per_split": False,
            "notes": (
                "This is appropriate for the current rule-based online forecaster. "
                "For future fitted ML models we should add explicit walk-forward retraining and, "
                "when horizons overlap materially, purging and embargo."
            ),
        },
        "forecastability": _forecastability_metrics(frame),
        "aggregate_signal": _aggregate_signal_metrics(frame),
    }
    return metrics_frame, summary


def _forecastability_metrics(frame: pd.DataFrame) -> dict[str, float]:
    returns = frame["asset_log_return"].dropna().astype(float).to_numpy()
    if returns.size < 5:
        return {}

    metrics = {
        "lag1_autocorrelation": _safe_autocorrelation(returns, 1),
        "variance_ratio_5": _variance_ratio(returns, 5),
        "variance_ratio_20": _variance_ratio(returns, 20),
        "spectral_entropy": _spectral_entropy(returns),
    }
    return metrics


def _aggregate_signal_metrics(frame: pd.DataFrame) -> dict[str, float]:
    metrics: dict[str, float] = {}
    realized_columns = sorted(
        (
            column for column in frame.columns
            if column.startswith("realized_return_h")
        ),
        key=lambda name: int(name.removeprefix("realized_return_h")),
    )
    primary_realized_column = realized_columns[0] if realized_columns else None
    if "aggregate_score" in frame.columns and primary_realized_column:
        sample = frame[["aggregate_score", primary_realized_column]].dropna()
        if not sample.empty and sample.shape[0] > 1:
            horizon = primary_realized_column.removeprefix("realized_return_h")
            metrics["aggregate_score_vs_primary_horizon_correlation"] = float(
                np.corrcoef(sample["aggregate_score"].astype(float), sample[primary_realized_column].astype(float))[0, 1]
            )
            metrics["aggregate_score_directional_accuracy_primary_horizon"] = float(
                np.mean(
                    np.sign(sample["aggregate_score"].astype(float))
                    == np.sign(sample[primary_realized_column].astype(float))
                )
            )
            metrics["aggregate_primary_horizon_bars"] = float(horizon)
    if "signal_confidence" in frame.columns and primary_realized_column:
        sample = frame[["signal_confidence", primary_realized_column]].dropna()
        if not sample.empty and sample.shape[0] > 1:
            metrics["confidence_vs_abs_realized_primary_horizon_correlation"] = float(
                np.corrcoef(
                    sample["signal_confidence"].astype(float),
                    np.abs(sample[primary_realized_column].astype(float)),
                )[0, 1]
            )
    return metrics


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


def load_backtest_steps(artifact_dir: str | Path) -> pd.DataFrame:
    return pd.read_csv(Path(artifact_dir) / "steps.csv")
