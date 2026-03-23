from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor
from catboost import Pool
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge


@dataclass(slots=True)
class PanelForecastConfig:
    horizons: list[int]
    model_family: str = "gradient_boosting"
    min_train_dates: int = 80
    max_train_dates: int | None = None
    retrain_every_dates: int = 5
    n_estimators: int = 60
    learning_rate: float = 0.05
    max_depth: int = 2
    ridge_alpha: float = 1.0
    catboost_iterations: int = 600
    catboost_depth: int = 6
    catboost_l2_leaf_reg: float = 3.0
    catboost_random_strength: float = 1.0
    catboost_bagging_temperature: float = 1.0
    catboost_loss_function: str = "RMSE"
    catboost_eval_metric: str = "RMSE"
    catboost_early_stopping_rounds: int = 50
    catboost_validation_fraction: float = 0.15
    catboost_thread_count: int = -1
    random_state: int = 7
    include_symbol_identity: bool = False
    include_bucket_metadata: bool = True


def evaluate_global_panel_forecast(
    panel_frame: pd.DataFrame,
    *,
    config: PanelForecastConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    if panel_frame.empty:
        raise ValueError("Panel frame is empty.")

    working = panel_frame.copy()
    working["timestamp"] = pd.to_datetime(working["timestamp"])
    working = working.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

    feature_columns = [column for column in working.columns if column.startswith("feature_")]
    context_columns = [column for column in working.columns if column.startswith("context_")]
    base_numeric_columns = feature_columns + context_columns
    categorical_columns: list[str] = []
    if config.include_symbol_identity and "symbol" in working.columns:
        categorical_columns.append("symbol")
    if config.include_bucket_metadata:
        categorical_columns.extend(
            [
                column for column in ["asset_class", "universe_bucket", "sub_bucket", "liquidity_bucket"]
                if column in working.columns
            ]
        )
    unique_dates = sorted(working["timestamp"].dropna().unique())
    if len(unique_dates) <= config.min_train_dates:
        raise ValueError("Not enough unique dates in the panel frame for the requested training window.")

    base_feature_frame = pd.get_dummies(working[base_numeric_columns + categorical_columns], columns=categorical_columns, dtype=float)
    base_feature_frame = base_feature_frame.replace([np.inf, -np.inf], np.nan)
    base_feature_frame = base_feature_frame.fillna(0.0)
    catboost_feature_frame = _build_catboost_feature_frame(
        working=working,
        numeric_columns=base_numeric_columns,
        categorical_columns=categorical_columns,
    )
    predictions_frame = working[["timestamp", "symbol"]].copy()
    retrain_counts: dict[int, int] = {horizon: 0 for horizon in config.horizons}

    for horizon in config.horizons:
        target_column = f"target_log_return_h{horizon}"
        if target_column not in working.columns:
            raise KeyError(f"Panel frame missing required target column: {target_column}")
        forecast_column = f"panel_pred_h{horizon}"
        predictions_frame[forecast_column] = np.nan

        model: Any | None = None
        train_columns: list[str] | None = None
        catboost_columns: list[str] | None = None

        for date_index in range(config.min_train_dates, len(unique_dates)):
            current_date = unique_dates[date_index]
            train_start_index = 0
            if config.max_train_dates and config.max_train_dates > 0:
                train_start_index = max(0, date_index - config.max_train_dates)
            train_dates = unique_dates[train_start_index:date_index]
            train_mask = working["timestamp"].isin(train_dates) & working[target_column].notna()
            test_mask = working["timestamp"] == current_date

            if not np.any(test_mask):
                continue

            should_refit = (
                model is None
                or (date_index - config.min_train_dates) % max(config.retrain_every_dates, 1) == 0
            )
            if should_refit:
                if config.model_family == "catboost":
                    train_indices = np.flatnonzero(train_mask.to_numpy())
                    if train_indices.size == 0:
                        continue
                    x_train_raw = catboost_feature_frame.iloc[train_indices].copy()
                    y_train_raw = working.loc[train_mask, target_column].astype(float).reset_index(drop=True)
                    fit_result = _fit_catboost_model(
                        x_train=x_train_raw,
                        y_train=y_train_raw,
                        categorical_columns=categorical_columns,
                        config=config,
                    )
                    if fit_result is None:
                        continue
                    model, catboost_columns = fit_result
                    retrain_counts[horizon] += 1
                else:
                    x_train = base_feature_frame.loc[train_mask]
                    y_train = working.loc[train_mask, target_column].astype(float)
                    if x_train.empty:
                        continue
                    model = _build_model(config)
                    model.fit(x_train, y_train)
                    train_columns = list(x_train.columns)
                    retrain_counts[horizon] += 1

            if model is None:
                continue

            if config.model_family == "catboost":
                if catboost_columns is None:
                    continue
                x_test_raw = catboost_feature_frame.loc[test_mask, catboost_columns].copy()
                test_pool = Pool(
                    data=x_test_raw,
                    cat_features=[x_test_raw.columns.get_loc(column) for column in categorical_columns if column in x_test_raw.columns],
                )
                predictions_frame.loc[test_mask, forecast_column] = model.predict(test_pool)
            else:
                if train_columns is None:
                    continue
                x_test = base_feature_frame.loc[test_mask, train_columns]
                predictions_frame.loc[test_mask, forecast_column] = model.predict(x_test)

    overall_metrics = _panel_metrics_overall(working, predictions_frame, config.horizons)
    symbol_metrics = _panel_metrics_by_symbol(working, predictions_frame, config.horizons)
    summary = {
        "model_family": _summary_model_family(config),
        "config": {
            "horizons": config.horizons,
            "model_family": config.model_family,
            "min_train_dates": config.min_train_dates,
            "max_train_dates": config.max_train_dates or 0,
            "retrain_every_dates": config.retrain_every_dates,
            "n_estimators": config.n_estimators,
            "learning_rate": config.learning_rate,
            "max_depth": config.max_depth,
            "ridge_alpha": config.ridge_alpha,
            "catboost_iterations": config.catboost_iterations,
            "catboost_depth": config.catboost_depth,
            "catboost_l2_leaf_reg": config.catboost_l2_leaf_reg,
            "catboost_random_strength": config.catboost_random_strength,
            "catboost_bagging_temperature": config.catboost_bagging_temperature,
            "catboost_loss_function": config.catboost_loss_function,
            "catboost_eval_metric": config.catboost_eval_metric,
            "catboost_early_stopping_rounds": config.catboost_early_stopping_rounds,
            "catboost_validation_fraction": config.catboost_validation_fraction,
            "catboost_thread_count": config.catboost_thread_count,
            "random_state": config.random_state,
            "include_symbol_identity": config.include_symbol_identity,
            "include_bucket_metadata": config.include_bucket_metadata,
        },
        "rows": int(len(working)),
        "symbols": int(working["symbol"].nunique()),
        "unique_dates": int(len(unique_dates)),
        "retrain_counts": retrain_counts,
        "feature_columns": feature_columns,
        "context_columns": context_columns,
        "categorical_columns": categorical_columns,
    }
    output_predictions = working.merge(predictions_frame, on=["timestamp", "symbol"], how="left")
    return output_predictions, overall_metrics, symbol_metrics, summary


def save_panel_forecast_artifacts(
    predictions_frame: pd.DataFrame,
    overall_metrics: pd.DataFrame,
    symbol_metrics: pd.DataFrame,
    summary: dict[str, Any],
    *,
    output_dir: str | Path,
) -> Path:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    predictions_frame.to_csv(artifact_dir / "panel_predictions.csv", index=False)
    overall_metrics.to_csv(artifact_dir / "overall_metrics.csv", index=False)
    symbol_metrics.to_csv(artifact_dir / "symbol_metrics.csv", index=False)
    (artifact_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return artifact_dir


def default_panel_forecast_output_dir() -> Path:
    stamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "panel_forecasts" / f"run_{stamp}"


def load_panel_dataset(dataset_dir: str | Path) -> pd.DataFrame:
    return pd.read_csv(Path(dataset_dir) / "panel_dataset.csv")


def _build_model(config: PanelForecastConfig) -> Any:
    if config.model_family == "gradient_boosting":
        return GradientBoostingRegressor(
            n_estimators=config.n_estimators,
            learning_rate=config.learning_rate,
            max_depth=config.max_depth,
            random_state=config.random_state,
            loss="squared_error",
        )
    if config.model_family == "linear_ridge":
        return Ridge(alpha=config.ridge_alpha, random_state=config.random_state)
    raise ValueError(f"Unsupported panel model family: {config.model_family}")


def _summary_model_family(config: PanelForecastConfig) -> str:
    if config.model_family == "linear_ridge":
        return "global_multivariate_linear_ridge"
    if config.model_family == "catboost":
        return "global_multivariate_catboost"
    return "global_multivariate_gradient_boosting"


def _build_catboost_feature_frame(
    *,
    working: pd.DataFrame,
    numeric_columns: list[str],
    categorical_columns: list[str],
) -> pd.DataFrame:
    frame = working[numeric_columns + categorical_columns].copy()
    for column in numeric_columns:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    for column in categorical_columns:
        frame[column] = frame[column].astype(str).fillna("missing")
    return frame


def _fit_catboost_model(
    *,
    x_train: pd.DataFrame,
    y_train: pd.Series,
    categorical_columns: list[str],
    config: PanelForecastConfig,
) -> tuple[CatBoostRegressor, list[str]] | None:
    if x_train.empty:
        return None
    validation_size = max(int(len(x_train) * config.catboost_validation_fraction), 1)
    if len(x_train) <= validation_size + 16:
        validation_size = max(1, min(len(x_train) // 5, len(x_train) - 1))
    train_size = len(x_train) - validation_size
    if train_size <= 0:
        return None

    x_fit = x_train.iloc[:train_size].copy()
    y_fit = y_train.iloc[:train_size].copy()
    x_valid = x_train.iloc[train_size:].copy()
    y_valid = y_train.iloc[train_size:].copy()
    cat_indices = [x_train.columns.get_loc(column) for column in categorical_columns if column in x_train.columns]

    fit_pool = Pool(data=x_fit, label=y_fit, cat_features=cat_indices)
    valid_pool = Pool(data=x_valid, label=y_valid, cat_features=cat_indices)
    model = CatBoostRegressor(
        loss_function=config.catboost_loss_function,
        eval_metric=config.catboost_eval_metric,
        iterations=config.catboost_iterations,
        depth=config.catboost_depth,
        learning_rate=config.learning_rate,
        l2_leaf_reg=config.catboost_l2_leaf_reg,
        random_strength=config.catboost_random_strength,
        bagging_temperature=config.catboost_bagging_temperature,
        has_time=True,
        bootstrap_type="Bayesian",
        grow_policy="SymmetricTree",
        thread_count=config.catboost_thread_count,
        random_seed=config.random_state,
        verbose=False,
    )
    model.fit(
        fit_pool,
        eval_set=valid_pool,
        use_best_model=True,
        early_stopping_rounds=config.catboost_early_stopping_rounds,
    )
    return model, list(x_train.columns)


def _panel_metrics_overall(
    panel_frame: pd.DataFrame,
    predictions_frame: pd.DataFrame,
    horizons: list[int],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        target_column = f"target_log_return_h{horizon}"
        pred_column = f"panel_pred_h{horizon}"
        sample = predictions_frame[[pred_column]].join(panel_frame[[target_column]]).dropna()
        purged_sample = _purged_panel_sample(sample, horizon=horizon)
        rows.append(
            {
                "scope": "overall",
                "horizon_bars": horizon,
                **_forecast_metric_payload(
                    forecasts=sample[pred_column].astype(float).to_numpy(),
                    realized=sample[target_column].astype(float).to_numpy(),
                    purged_forecasts=purged_sample[pred_column].astype(float).to_numpy() if not purged_sample.empty else np.array([], dtype=float),
                    purged_realized=purged_sample[target_column].astype(float).to_numpy() if not purged_sample.empty else np.array([], dtype=float),
                ),
            }
        )
    return pd.DataFrame(rows)


def _panel_metrics_by_symbol(
    panel_frame: pd.DataFrame,
    predictions_frame: pd.DataFrame,
    horizons: list[int],
) -> pd.DataFrame:
    merged = panel_frame[["timestamp", "symbol"]].merge(predictions_frame, on=["timestamp", "symbol"], how="left")
    source = panel_frame.merge(merged, on=["timestamp", "symbol"], how="left")
    rows: list[dict[str, object]] = []
    for symbol, symbol_frame in source.groupby("symbol", sort=True):
        for horizon in horizons:
            target_column = f"target_log_return_h{horizon}"
            pred_column = f"panel_pred_h{horizon}"
            sample = symbol_frame[[pred_column, target_column]].dropna()
            purged_sample = _purged_panel_sample(sample, horizon=horizon)
            rows.append(
                {
                    "symbol": symbol,
                    "horizon_bars": horizon,
                    **_forecast_metric_payload(
                        forecasts=sample[pred_column].astype(float).to_numpy(),
                        realized=sample[target_column].astype(float).to_numpy(),
                        purged_forecasts=purged_sample[pred_column].astype(float).to_numpy() if not purged_sample.empty else np.array([], dtype=float),
                        purged_realized=purged_sample[target_column].astype(float).to_numpy() if not purged_sample.empty else np.array([], dtype=float),
                    ),
                }
            )
    return pd.DataFrame(rows)


def _forecast_metric_payload(
    *,
    forecasts: np.ndarray,
    realized: np.ndarray,
    purged_forecasts: np.ndarray,
    purged_realized: np.ndarray,
) -> dict[str, float]:
    if forecasts.size == 0:
        return {
            "observations": 0,
            "purged_observations": 0,
            "correlation": math.nan,
            "purged_correlation": math.nan,
            "mae": math.nan,
            "purged_mae": math.nan,
            "rmse": math.nan,
            "purged_rmse": math.nan,
            "bias": math.nan,
            "directional_accuracy": math.nan,
            "purged_directional_accuracy": math.nan,
        }
    correlation = (
        float(np.corrcoef(forecasts, realized)[0, 1])
        if forecasts.size > 1 and np.std(forecasts) > 0 and np.std(realized) > 0
        else math.nan
    )
    purged_correlation = (
        float(np.corrcoef(purged_forecasts, purged_realized)[0, 1])
        if purged_forecasts.size > 1 and np.std(purged_forecasts) > 0 and np.std(purged_realized) > 0
        else math.nan
    )
    return {
        "observations": int(forecasts.size),
        "purged_observations": int(purged_forecasts.size),
        "correlation": correlation,
        "purged_correlation": purged_correlation,
        "mae": float(np.mean(np.abs(forecasts - realized))),
        "purged_mae": float(np.mean(np.abs(purged_forecasts - purged_realized))) if purged_forecasts.size else math.nan,
        "rmse": float(np.sqrt(np.mean(np.square(forecasts - realized)))),
        "purged_rmse": float(np.sqrt(np.mean(np.square(purged_forecasts - purged_realized)))) if purged_forecasts.size else math.nan,
        "bias": float(np.mean(forecasts - realized)),
        "directional_accuracy": float(np.mean(np.sign(forecasts) == np.sign(realized))),
        "purged_directional_accuracy": float(np.mean(np.sign(purged_forecasts) == np.sign(purged_realized))) if purged_forecasts.size else math.nan,
    }


def _purged_panel_sample(sample: pd.DataFrame, *, horizon: int, embargo_bars: int | None = None) -> pd.DataFrame:
    if sample.empty:
        return sample
    stride = max(1, horizon + (embargo_bars if embargo_bars is not None else max(1, horizon // 5)))
    selected_rows = []
    next_allowed = 0
    for idx in range(len(sample)):
        if idx < next_allowed:
            continue
        selected_rows.append(idx)
        next_allowed = idx + stride
    return sample.iloc[selected_rows].reset_index(drop=True)
