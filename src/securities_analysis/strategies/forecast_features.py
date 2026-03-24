from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np


FeatureBuilder = Callable[["_FeatureContext"], float]


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    name: str
    family: str
    builder: FeatureBuilder


@dataclass(slots=True)
class _FeatureContext:
    closes: np.ndarray
    returns: np.ndarray
    periods_per_year: int
    lookback_bars: int
    vol_lookback_bars: int
    timestamp: datetime
    ma_5: float
    ma_10: float
    ma_20: float
    ma_long: float
    recent_returns_5: np.ndarray
    recent_returns_10: np.ndarray
    recent_returns_20: np.ndarray
    long_closes: np.ndarray
    rolling_peak: float
    rolling_trough: float
    high_distance: float
    low_distance: float
    drawdown_duration: float
    rolling_range_20: float
    close_scale: float
    range_compression_20: float
    vol_5: float
    vol_20: float
    vol_long: float
    vol_of_vol_20: float
    sign_streak: float
    weekday: int
    month: int
    year_progress: float
    gfc_crisis_flag: float
    post_gfc_flag: float
    euro_crisis_flag: float
    covid_crisis_flag: float
    post_covid_flag: float
    inflation_shock_flag: float
    years_since_gfc: float
    years_since_covid: float

    def cumulative_log_return(self, window: int) -> float:
        window = min(window, len(self.returns))
        return float(np.sum(self.returns[-window:]))


def _annualized_vol(returns: np.ndarray, *, periods_per_year: int, window: int) -> float:
    window = min(window, len(returns))
    if window < 2:
        return 0.0
    return float(np.std(returns[-window:], ddof=1) * np.sqrt(periods_per_year))


def _moving_average(closes: np.ndarray, *, window: int) -> float:
    window = min(window, len(closes))
    return float(np.mean(closes[-window:]))


def _rolling_arg_distance(values: np.ndarray, fn) -> float:
    idx = int(fn(values))
    return float(len(values) - 1 - idx)


def _safe_log_ratio(numerator: float, denominator: float) -> float:
    return float(np.log(max(numerator, 1e-8) / max(denominator, 1e-8)))


def _feature_specs() -> list[FeatureSpec]:
    specs = [
        FeatureSpec("ret_3", "price_state", lambda c: c.cumulative_log_return(3)),
        FeatureSpec("ret_5", "price_state", lambda c: c.cumulative_log_return(5)),
        FeatureSpec("ret_10", "price_state", lambda c: c.cumulative_log_return(10)),
        FeatureSpec("ret_20", "price_state", lambda c: c.cumulative_log_return(20)),
        FeatureSpec("ret_long", "price_state", lambda c: c.cumulative_log_return(c.lookback_bars)),
        FeatureSpec("vol_5", "volatility_state", lambda c: c.vol_5),
        FeatureSpec("vol_20", "volatility_state", lambda c: c.vol_20),
        FeatureSpec("vol_long", "volatility_state", lambda c: c.vol_long),
        FeatureSpec("vol_ratio_short_long", "volatility_state", lambda c: c.vol_5 / max(c.vol_long, 1e-8)),
        FeatureSpec("vol_of_vol_20", "volatility_state", lambda c: c.vol_of_vol_20),
        FeatureSpec("ma_spread_5_20", "trend_structure", lambda c: _safe_log_ratio(c.ma_5, c.ma_20)),
        FeatureSpec("ma_spread_10_long", "trend_structure", lambda c: _safe_log_ratio(c.ma_10, c.ma_long)),
        FeatureSpec(
            "ma_slope_5",
            "trend_structure",
            lambda c: _safe_log_ratio(float(c.closes[-1]), float(c.closes[-min(6, len(c.closes))])),
        ),
        FeatureSpec(
            "ma_slope_20",
            "trend_structure",
            lambda c: _safe_log_ratio(float(c.closes[-1]), float(c.closes[-min(21, len(c.closes))])),
        ),
        FeatureSpec("drawdown_depth", "downside_state", lambda c: _safe_log_ratio(float(c.closes[-1]), c.rolling_peak)),
        FeatureSpec("drawdown_duration", "downside_state", lambda c: c.drawdown_duration),
        FeatureSpec("days_since_high", "downside_state", lambda c: c.high_distance),
        FeatureSpec("days_since_low", "downside_state", lambda c: c.low_distance),
        FeatureSpec(
            "breakout_distance_5",
            "downside_state",
            lambda c: _safe_log_ratio(float(c.closes[-1]), float(np.max(c.closes[-5:]))),
        ),
        FeatureSpec("range_compression_20", "downside_state", lambda c: c.range_compression_20),
        FeatureSpec("up_day_fraction_5", "persistence_state", lambda c: float(np.mean(c.recent_returns_5 > 0))),
        FeatureSpec("up_day_fraction_20", "persistence_state", lambda c: float(np.mean(c.recent_returns_20 > 0))),
        FeatureSpec("sign_streak_10", "persistence_state", lambda c: c.sign_streak),
        FeatureSpec("dow_sin", "calendar_state", lambda c: float(np.sin(2.0 * np.pi * c.weekday / 7.0))),
        FeatureSpec("dow_cos", "calendar_state", lambda c: float(np.cos(2.0 * np.pi * c.weekday / 7.0))),
        FeatureSpec("month_sin", "calendar_state", lambda c: float(np.sin(2.0 * np.pi * (c.month - 1) / 12.0))),
        FeatureSpec("month_cos", "calendar_state", lambda c: float(np.cos(2.0 * np.pi * (c.month - 1) / 12.0))),
        FeatureSpec("year_progress", "calendar_state", lambda c: c.year_progress),
        FeatureSpec("gfc_crisis_flag", "regime_state", lambda c: c.gfc_crisis_flag),
        FeatureSpec("post_gfc_flag", "regime_state", lambda c: c.post_gfc_flag),
        FeatureSpec("euro_crisis_flag", "regime_state", lambda c: c.euro_crisis_flag),
        FeatureSpec("covid_crisis_flag", "regime_state", lambda c: c.covid_crisis_flag),
        FeatureSpec("post_covid_flag", "regime_state", lambda c: c.post_covid_flag),
        FeatureSpec("inflation_shock_flag", "regime_state", lambda c: c.inflation_shock_flag),
        FeatureSpec("years_since_gfc", "regime_state", lambda c: c.years_since_gfc),
        FeatureSpec("years_since_covid", "regime_state", lambda c: c.years_since_covid),
    ]
    return specs


FEATURE_SPECS: tuple[FeatureSpec, ...] = tuple(_feature_specs())
FEATURE_SPEC_BY_NAME: dict[str, FeatureSpec] = {spec.name: spec for spec in FEATURE_SPECS}
FEATURE_FAMILY_MAP: dict[str, tuple[str, ...]] = {
    family: tuple(spec.name for spec in FEATURE_SPECS if spec.family == family)
    for family in OrderedDict.fromkeys(spec.family for spec in FEATURE_SPECS)
}
DEFAULT_FEATURE_FAMILIES: tuple[str, ...] = tuple(FEATURE_FAMILY_MAP)
FEATURE_PRESET_MAP: dict[str, tuple[str, ...]] = {
    "all": DEFAULT_FEATURE_FAMILIES,
    "momentum_core": (
        "price_state",
        "volatility_state",
        "trend_structure",
        "downside_state",
        "persistence_state",
        "regime_state",
    ),
    "momentum_minimal": (
        "price_state",
        "volatility_state",
        "trend_structure",
    ),
    "mean_reversion_core": (
        "price_state",
        "volatility_state",
        "downside_state",
        "persistence_state",
        "calendar_state",
        "regime_state",
    ),
}


def forecast_feature_families() -> dict[str, list[str]]:
    return {family: list(names) for family, names in FEATURE_FAMILY_MAP.items()}


def forecast_feature_presets() -> dict[str, list[str]]:
    return {preset: list(families) for preset, families in FEATURE_PRESET_MAP.items()}


def forecast_feature_names(*, families: list[str] | tuple[str, ...] | None = None) -> list[str]:
    selected_specs = _select_feature_specs(families=families)
    return [spec.name for spec in selected_specs]


def forecast_feature_family_by_name() -> dict[str, str]:
    return {spec.name: spec.family for spec in FEATURE_SPECS}


def resolve_feature_families(
    *,
    families: list[str] | tuple[str, ...] | None = None,
    preset: str | None = None,
) -> list[str]:
    resolved: list[str] = []
    if preset:
        if preset not in FEATURE_PRESET_MAP:
            raise KeyError(f"Unknown forecast feature preset: {preset}")
        resolved.extend(FEATURE_PRESET_MAP[preset])
    if families:
        resolved.extend(list(families))
    if not resolved:
        return list(DEFAULT_FEATURE_FAMILIES)
    deduped: list[str] = []
    for family in resolved:
        if family not in FEATURE_FAMILY_MAP:
            raise KeyError(f"Unknown forecast feature family: {family}")
        if family not in deduped:
            deduped.append(family)
    return deduped


def build_forecast_feature_vector(
    closes: np.ndarray,
    *,
    periods_per_year: int,
    lookback_bars: int,
    vol_lookback_bars: int,
    timestamp: datetime,
    families: list[str] | tuple[str, ...] | None = None,
) -> np.ndarray | None:
    context = _build_feature_context(
        closes=closes,
        periods_per_year=periods_per_year,
        lookback_bars=lookback_bars,
        vol_lookback_bars=vol_lookback_bars,
        timestamp=timestamp,
    )
    if context is None:
        return None
    selected_specs = _select_feature_specs(families=families)
    values = [spec.builder(context) for spec in selected_specs]
    return np.asarray(values, dtype=float)


def _select_feature_specs(*, families: list[str] | tuple[str, ...] | None) -> tuple[FeatureSpec, ...]:
    if families is None:
        return FEATURE_SPECS
    requested = tuple(families)
    unknown = [family for family in requested if family not in FEATURE_FAMILY_MAP]
    if unknown:
        raise KeyError(f"Unknown forecast feature families: {', '.join(unknown)}")
    requested_set = set(requested)
    return tuple(spec for spec in FEATURE_SPECS if spec.family in requested_set)


def _build_feature_context(
    *,
    closes: np.ndarray,
    periods_per_year: int,
    lookback_bars: int,
    vol_lookback_bars: int,
    timestamp: datetime,
) -> _FeatureContext | None:
    if timestamp.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=None)
    returns = np.diff(np.log(closes))
    min_required = max(lookback_bars, vol_lookback_bars, 20)
    if len(returns) < min_required:
        return None

    long_window = min(lookback_bars, len(closes))
    ma_5 = _moving_average(closes, window=5)
    ma_10 = _moving_average(closes, window=10)
    ma_20 = _moving_average(closes, window=20)
    ma_long = _moving_average(closes, window=long_window)

    recent_returns_5 = returns[-min(5, len(returns)) :]
    recent_returns_10 = returns[-min(10, len(returns)) :]
    recent_returns_20 = returns[-min(20, len(returns)) :]
    long_closes = closes[-long_window:]
    rolling_peak = float(np.max(long_closes))
    rolling_trough = float(np.min(long_closes))
    high_distance = _rolling_arg_distance(long_closes, np.argmax)
    low_distance = _rolling_arg_distance(long_closes, np.argmin)
    peak_index = int(np.argmax(long_closes))
    drawdown_duration = float(len(long_closes) - 1 - peak_index)
    rolling_range_20 = float(np.max(closes[-20:]) - np.min(closes[-20:])) if len(closes) >= 20 else 0.0
    close_scale = max(float(closes[-1]), 1e-8)
    range_compression_20 = rolling_range_20 / close_scale
    vol_20 = _annualized_vol(returns, periods_per_year=periods_per_year, window=20)
    vol_long = _annualized_vol(returns, periods_per_year=periods_per_year, window=max(vol_lookback_bars, lookback_bars))
    vol_5 = _annualized_vol(returns, periods_per_year=periods_per_year, window=5)
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

    return _FeatureContext(
        closes=closes,
        returns=returns,
        periods_per_year=periods_per_year,
        lookback_bars=lookback_bars,
        vol_lookback_bars=vol_lookback_bars,
        timestamp=timestamp,
        ma_5=ma_5,
        ma_10=ma_10,
        ma_20=ma_20,
        ma_long=ma_long,
        recent_returns_5=recent_returns_5,
        recent_returns_10=recent_returns_10,
        recent_returns_20=recent_returns_20,
        long_closes=long_closes,
        rolling_peak=rolling_peak,
        rolling_trough=rolling_trough,
        high_distance=high_distance,
        low_distance=low_distance,
        drawdown_duration=drawdown_duration,
        rolling_range_20=rolling_range_20,
        close_scale=close_scale,
        range_compression_20=range_compression_20,
        vol_5=vol_5,
        vol_20=vol_20,
        vol_long=vol_long,
        vol_of_vol_20=vol_of_vol_20,
        sign_streak=sign_streak,
        weekday=weekday,
        month=month,
        year_progress=year_progress,
        gfc_crisis_flag=gfc_crisis_flag,
        post_gfc_flag=post_gfc_flag,
        euro_crisis_flag=euro_crisis_flag,
        covid_crisis_flag=covid_crisis_flag,
        post_covid_flag=post_covid_flag,
        inflation_shock_flag=inflation_shock_flag,
        years_since_gfc=years_since_gfc,
        years_since_covid=years_since_covid,
    )


def _in_window(timestamp: datetime, *, start: tuple[int, int, int], end: tuple[int, int, int]) -> bool:
    if timestamp.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=None)
    start_dt = datetime(*start)
    end_dt = datetime(*end)
    return start_dt <= timestamp <= end_dt
