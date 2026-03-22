from __future__ import annotations

from datetime import datetime

import numpy as np


def forecast_feature_names() -> list[str]:
    return [
        "ret_3",
        "ret_5",
        "ret_10",
        "ret_20",
        "ret_long",
        "vol_5",
        "vol_20",
        "vol_long",
        "vol_ratio_short_long",
        "ma_spread_5_20",
        "ma_spread_10_long",
        "ma_slope_5",
        "ma_slope_20",
        "drawdown_depth",
        "drawdown_duration",
        "days_since_high",
        "days_since_low",
        "breakout_distance_5",
        "range_compression_20",
        "vol_of_vol_20",
        "up_day_fraction_5",
        "up_day_fraction_20",
        "sign_streak_10",
        "dow_sin",
        "dow_cos",
        "month_sin",
        "month_cos",
        "year_progress",
        "gfc_crisis_flag",
        "post_gfc_flag",
        "euro_crisis_flag",
        "covid_crisis_flag",
        "post_covid_flag",
        "inflation_shock_flag",
        "years_since_gfc",
        "years_since_covid",
    ]


def build_forecast_feature_vector(
    closes: np.ndarray,
    *,
    periods_per_year: int,
    lookback_bars: int,
    vol_lookback_bars: int,
    timestamp: datetime,
) -> np.ndarray | None:
    if timestamp.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=None)
    returns = np.diff(np.log(closes))
    min_required = max(lookback_bars, vol_lookback_bars, 20)
    if len(returns) < min_required:
        return None

    def cumulative_log_return(window: int) -> float:
        window = min(window, len(returns))
        return float(np.sum(returns[-window:]))

    def annualized_vol(window: int) -> float:
        window = min(window, len(returns))
        if window < 2:
            return 0.0
        return float(np.std(returns[-window:], ddof=1) * np.sqrt(periods_per_year))

    def moving_average(window: int) -> float:
        window = min(window, len(closes))
        return float(np.mean(closes[-window:]))

    def rolling_arg_distance(values: np.ndarray, fn) -> float:
        idx = int(fn(values))
        return float(len(values) - 1 - idx)

    long_window = min(lookback_bars, len(closes))
    ma_5 = moving_average(5)
    ma_10 = moving_average(10)
    ma_20 = moving_average(20)
    ma_long = moving_average(long_window)

    recent_returns_5 = returns[-min(5, len(returns)) :]
    recent_returns_10 = returns[-min(10, len(returns)) :]
    recent_returns_20 = returns[-min(20, len(returns)) :]
    long_closes = closes[-long_window:]
    rolling_peak = float(np.max(long_closes))
    rolling_trough = float(np.min(long_closes))
    high_distance = rolling_arg_distance(long_closes, np.argmax)
    low_distance = rolling_arg_distance(long_closes, np.argmin)
    peak_index = int(np.argmax(long_closes))
    drawdown_duration = float(len(long_closes) - 1 - peak_index)
    rolling_range_20 = float(np.max(closes[-20:]) - np.min(closes[-20:])) if len(closes) >= 20 else 0.0
    close_scale = max(float(closes[-1]), 1e-8)
    range_compression_20 = rolling_range_20 / close_scale
    vol_20 = annualized_vol(20)
    vol_long = annualized_vol(max(vol_lookback_bars, lookback_bars))
    vol_5 = annualized_vol(5)
    vol_of_vol_20 = (
        float(np.std(np.abs(recent_returns_20), ddof=1) * np.sqrt(periods_per_year))
        if recent_returns_20.size > 1
        else 0.0
    )
    sign_streak = float(np.sum(np.sign(recent_returns_10))) / max(len(recent_returns_10), 1)

    weekday = timestamp.weekday()
    month = timestamp.month
    year_progress = float((timestamp.timetuple().tm_yday - 1) / 365.25)
    gfc_crisis_flag = float(_in_window(timestamp, start=(2008, 9, 1), end=(2009, 6, 30)))
    post_gfc_flag = float(timestamp >= datetime(2009, 7, 1))
    euro_crisis_flag = float(_in_window(timestamp, start=(2011, 7, 1), end=(2012, 7, 31)))
    covid_crisis_flag = float(_in_window(timestamp, start=(2020, 2, 15), end=(2020, 6, 30)))
    post_covid_flag = float(timestamp >= datetime(2020, 7, 1))
    inflation_shock_flag = float(_in_window(timestamp, start=(2021, 10, 1), end=(2023, 12, 31)))
    years_since_gfc = max((timestamp - datetime(2009, 3, 9)).days / 365.25, 0.0)
    years_since_covid = max((timestamp - datetime(2020, 3, 23)).days / 365.25, 0.0)

    return np.array(
        [
            cumulative_log_return(3),
            cumulative_log_return(5),
            cumulative_log_return(10),
            cumulative_log_return(20),
            cumulative_log_return(lookback_bars),
            vol_5,
            vol_20,
            vol_long,
            vol_5 / max(vol_long, 1e-8),
            np.log(max(ma_5, 1e-8) / max(ma_20, 1e-8)),
            np.log(max(ma_10, 1e-8) / max(ma_long, 1e-8)),
            np.log(max(closes[-1], 1e-8) / max(closes[-min(6, len(closes))], 1e-8)),
            np.log(max(closes[-1], 1e-8) / max(closes[-min(21, len(closes))], 1e-8)),
            np.log(max(closes[-1], 1e-8) / max(rolling_peak, 1e-8)),
            drawdown_duration,
            high_distance,
            low_distance,
            np.log(max(closes[-1], 1e-8) / max(np.max(closes[-5:]), 1e-8)),
            range_compression_20,
            vol_of_vol_20,
            float(np.mean(recent_returns_5 > 0)),
            float(np.mean(recent_returns_20 > 0)),
            sign_streak,
            float(np.sin(2.0 * np.pi * weekday / 7.0)),
            float(np.cos(2.0 * np.pi * weekday / 7.0)),
            float(np.sin(2.0 * np.pi * (month - 1) / 12.0)),
            float(np.cos(2.0 * np.pi * (month - 1) / 12.0)),
            year_progress,
            gfc_crisis_flag,
            post_gfc_flag,
            euro_crisis_flag,
            covid_crisis_flag,
            post_covid_flag,
            inflation_shock_flag,
            years_since_gfc,
            years_since_covid,
        ],
        dtype=float,
    )


def _in_window(timestamp: datetime, *, start: tuple[int, int, int], end: tuple[int, int, int]) -> bool:
    if timestamp.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=None)
    start_dt = datetime(*start)
    end_dt = datetime(*end)
    return start_dt <= timestamp <= end_dt
