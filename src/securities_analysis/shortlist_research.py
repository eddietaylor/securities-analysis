from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from securities_analysis.execution.history import HistoricalPriceProvider
from securities_analysis.forecastability_scan import scan_forecastability
from securities_analysis.panel import UniverseSymbol
from securities_analysis.panel import build_panel_dataset, save_panel_dataset
from securities_analysis.panel_forecast import (
    PanelForecastConfig,
    evaluate_global_panel_forecast,
    save_panel_forecast_artifacts,
)


@dataclass(slots=True)
class ShortlistResearchResult:
    shortlist_symbols: list[str]
    scan_artifact_dir: Path
    dataset_artifact_dir: Path
    forecast_artifact_dir: Path


def run_shortlist_research(
    *,
    history_provider: HistoricalPriceProvider,
    universe: list[UniverseSymbol],
    start: str,
    end: str,
    freq: str,
    top_n: int,
    include_symbols: list[str],
    lookback_bars: int,
    vol_lookback_bars: int,
    horizons: list[int],
    periods_per_year: int,
    model_config: PanelForecastConfig,
    output_dir: str | Path,
    feature_families: list[str] | tuple[str, ...] | None = None,
    feature_preset: str | None = None,
    enhanced_context_features: bool = False,
) -> ShortlistResearchResult:
    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    scan_frame = scan_forecastability(
        history_provider=history_provider,
        universe=universe,
        start=start,
        end=end,
        freq=freq,
    )
    scan_artifact_dir = artifact_dir / "scan"
    from securities_analysis.forecastability_scan import save_forecastability_scan
    save_forecastability_scan(
        scan_frame,
        output_dir=scan_artifact_dir,
        config={
            "start": start,
            "end": end,
            "freq": freq,
            "top_n": top_n,
            "include_symbols": include_symbols,
        },
    )

    shortlist_symbols = _select_shortlist_symbols(
        scan_frame=scan_frame,
        top_n=top_n,
        include_symbols=include_symbols,
    )
    metadata_map = {item.symbol: item for item in universe if item.symbol in shortlist_symbols}
    dataset_frame = build_panel_dataset(
        history_provider=history_provider,
        symbols=shortlist_symbols,
        asset_class=next(iter(metadata_map.values())).asset_class if metadata_map else "future",
        start=start,
        end=end,
        freq=freq,
        lookback_bars=lookback_bars,
        vol_lookback_bars=vol_lookback_bars,
        horizons=horizons,
        periods_per_year=periods_per_year,
        metadata_map=metadata_map,
        feature_families=feature_families,
        feature_preset=feature_preset,
        enhanced_context_features=enhanced_context_features,
    )
    dataset_artifact_dir = artifact_dir / "dataset"
    save_panel_dataset(
        dataset_frame,
        output_dir=dataset_artifact_dir,
        config={
            "symbols": shortlist_symbols,
            "start": start,
            "end": end,
            "freq": freq,
            "lookback_bars": lookback_bars,
            "vol_lookback_bars": vol_lookback_bars,
            "horizons": horizons,
            "feature_families": list(feature_families) if feature_families else [],
            "feature_preset": feature_preset or "",
            "enhanced_context_features": enhanced_context_features,
        },
    )

    predictions_frame, overall_metrics, symbol_metrics, summary = evaluate_global_panel_forecast(
        dataset_frame,
        config=model_config,
    )
    forecast_artifact_dir = artifact_dir / "forecast"
    save_panel_forecast_artifacts(
        predictions_frame,
        overall_metrics,
        symbol_metrics,
        summary,
        output_dir=forecast_artifact_dir,
    )

    (artifact_dir / "summary.json").write_text(
        json.dumps(
            {
                "shortlist_symbols": shortlist_symbols,
                "scan_artifact_dir": str(scan_artifact_dir),
                "dataset_artifact_dir": str(dataset_artifact_dir),
                "forecast_artifact_dir": str(forecast_artifact_dir),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    return ShortlistResearchResult(
        shortlist_symbols=shortlist_symbols,
        scan_artifact_dir=scan_artifact_dir,
        dataset_artifact_dir=dataset_artifact_dir,
        forecast_artifact_dir=forecast_artifact_dir,
    )


def default_shortlist_research_output_dir() -> Path:
    stamp = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "shortlist_research" / f"run_{stamp}"


def _select_shortlist_symbols(
    *,
    scan_frame: pd.DataFrame,
    top_n: int,
    include_symbols: list[str],
) -> list[str]:
    ranked = scan_frame["symbol"].head(top_n).tolist() if not scan_frame.empty else []
    ordered: list[str] = []
    for symbol in ranked + include_symbols:
        if symbol and symbol not in ordered:
            ordered.append(symbol)
    return ordered
