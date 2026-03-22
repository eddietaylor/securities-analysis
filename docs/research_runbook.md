# Research Runbook

## First Sweep

The first batch research pass should stay intentionally simple:

- liquid U.S. ETFs only
- daily bars
- one year of history to validate the pipeline
- a moderate parameter grid, not a giant brute-force search

Recommended first symbol set:

- `SPY`
- `QQQ`
- `IWM`
- `DIA`
- `TLT`
- `GLD`

These give us:

- broad equities
- growth-heavy equities
- small caps
- large-cap industrials
- long-duration bonds
- gold

This is not yet a portfolio construction step. It is a research sanity check across regimes and instrument types.

## Recommended Command

Use the provided script:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_first_research_sweep.ps1
```

Or run the CLI directly:

```powershell
$env:PYTHONPATH="src"
python -m securities_analysis `
  --cfg data\alpaca_keys.cfg `
  research `
  --symbols SPY,QQQ,IWM,DIA,TLT,GLD `
  --asset-class equity `
  --start 2024-01-01 `
  --end 2024-12-31 `
  --freq day `
  --spread-bps 1.0 `
  --commission-bps 0.0 `
  --slippage-bps 2.0 `
  --market-impact-bps-per-turnover 5.0 `
  --lookback-bars-grid 20,30,60 `
  --vol-lookback-bars-grid 10,20 `
  --target-volatility-grid 0.10,0.20 `
  --max-gross-leverage-grid 1.0 `
  --max-position-notional-pct-grid 0.10,0.20 `
  --max-trade-notional-pct-grid 0.05,0.10 `
  --max-daily-drawdown-pct-grid 0.02,0.03 `
  --max-spread-bps-grid 20.0 `
  --fractional-kelly-grid 0.10,0.25 `
  --max-kelly-fraction-grid 0.25,0.50 `
  --rank-by sharpe_ratio `
  --top-n 10 `
  --save-top-run-artifacts
```

## What This Sweep Is For

The goal is not to find the "best" strategy immediately.

The goal is to answer:

- does the current framework produce stable, believable rankings?
- do any parameter clusters look robust across multiple symbols?
- is the current sizing layer too conservative or appropriately defensive?
- are the best results concentrated in one symbol, which would be a warning sign?
- does the strategy beat buy-and-hold of the same symbol?
- does the strategy beat a market benchmark proxy such as `SPY`?

## What To Inspect After The Run

Start with:

- `leaderboard.csv`
- `leaderboard_deduped.csv`
- `leaderboard_top.json`
- `leaderboard_deduped_top.json`
- `summary.json`
- `summary_by_symbol.csv`
- `summary_by_parameters.csv`

Benchmark columns to inspect:

- `symbol_buy_hold_cumulative_return`
- `market_buy_hold_cumulative_return`
- `excess_return_vs_symbol_buy_hold`
- `excess_return_vs_market_buy_hold`
- `symbol_buy_hold_sharpe_ratio`
- `market_buy_hold_sharpe_ratio`
- `excess_sharpe_vs_symbol_buy_hold`
- `excess_sharpe_vs_market_buy_hold`

If `--save-top-run-artifacts` was used, inspect the top few run folders:

- `summary.json`
- `steps.csv`
- `equity_drawdown.png`

## What Good Looks Like

- the better runs are not all on one single symbol
- the deduped leaderboard still looks strong after removing equivalent outcomes
- the top runs beat their own symbol buy-and-hold, not just weaker alternatives
- the top runs are competitive versus the market benchmark, not only versus themselves
- the top runs do not rely on absurdly low trade counts
- Sharpe and Calmar improve together instead of fighting each other
- max drawdown stays believable
- results remain decent under nonzero slippage assumptions

## What Bad Looks Like

- one extreme parameter set dominates only one symbol
- the non-deduped leaderboard looks amazing but the deduped leaderboard collapses
- a strategy ranks highly but still loses to buy-and-hold
- top rankings collapse when costs are nontrivial
- high returns show up with unstable or ugly drawdowns
- leaderboard quality is driven by tiny sample quirks instead of repeatable structure

## Next Step After The First Sweep

If the first sweep looks coherent, the next move is:

1. shrink the search around the best parameter neighborhoods
2. compare 2024 against an additional date range
3. add a second research universe rather than immediately adding a second strategy

## Multi-Period Comparison

Single-period results are not enough. The next standard is to compare the same sweep across multiple windows.

Recommended first comparison set:

- `2023-01-01:2023-12-31`
- `2024-01-01:2024-12-31`
- `2025-01-01:2025-12-31`

Example:

```powershell
$env:PYTHONPATH="src"
python -m securities_analysis `
  --cfg data\alpaca_keys.cfg `
  research `
  --symbols SPY,QQQ,IWM,DIA,TLT,GLD `
  --asset-class equity `
  --periods 2023-01-01:2023-12-31,2024-01-01:2024-12-31,2025-01-01:2025-12-31 `
  --freq day `
  --spread-bps 1.0 `
  --commission-bps 0.0 `
  --slippage-bps 2.0 `
  --market-impact-bps-per-turnover 5.0 `
  --lookback-bars-grid 20,30,60 `
  --vol-lookback-bars-grid 10,20 `
  --target-volatility-grid 0.10,0.20 `
  --max-gross-leverage-grid 1.0 `
  --max-position-notional-pct-grid 0.10,0.20 `
  --max-trade-notional-pct-grid 0.05,0.10 `
  --max-daily-drawdown-pct-grid 0.02,0.03 `
  --max-spread-bps-grid 20.0 `
  --fractional-kelly-grid 0.10,0.25 `
  --max-kelly-fraction-grid 0.25,0.50 `
  --rank-by sharpe_ratio `
  --top-n 10
```

Additional files to inspect after a multi-period run:

- `summary_by_period.csv`
- `summary_by_symbol_period.csv`

What we want:

- good symbols and parameter neighborhoods remain competitive across periods
- benchmark-relative performance does not disappear outside one calendar year

## Panel-Training Universe

If we move from local single-symbol forecasting toward panel-style ML, we need an explicit first universe.

### First Recommended Universe

Use a curated liquid ETF panel first:

- broad equity:
  - `SPY`
  - `QQQ`
  - `IWM`
  - `DIA`
- rates:
  - `TLT`
  - `IEF`
- metals:
  - `GLD`
  - `SLV`
- sectors:
  - `XLK`
  - `XLF`
  - `XLE`
  - `XLU`

Optional second-wave additions:

- `EEM`
- `FXI`

Why this universe:

- strong liquidity
- clean histories
- broad regime diversity
- tradable in the current stack
- enough cross-sectional variety to support panel-style forecasting

### Universe Filters

Before admitting a symbol to the panel universe, check:

- history length
- average dollar volume
- spread quality
- broker tradability
- absence of obvious structural pathologies

### Universe Metadata

Store at least:

- `symbol`
- `asset_class`
- `sub_class`
- `sector_or_theme`
- `liquidity_bucket`
- `volatility_bucket`

This metadata should later be usable as model inputs or conditioning variables.

### Research Use

Use this universe for:

- multi-symbol forecastability comparison
- panel-style model training
- local-vs-global forecasting comparisons

Do not immediately expand to a huge stock universe until:

- the panel dataset builder exists
- the validation protocol is stable
- the local baselines and global baseline can be compared honestly

## Panel Dataset Builder

The repo now has a first panel-dataset CLI path for global / panel-style forecasting research.

Example:

```powershell
$env:PYTHONPATH="src"
python -m securities_analysis `
  --cfg data\alpaca_keys.cfg `
  panel-dataset `
  --symbols SPY,QQQ,IWM,DIA,TLT,IEF,GLD,SLV,XLK,XLF,XLE,XLU `
  --asset-class equity `
  --start 2018-01-01 `
  --end 2024-12-31 `
  --freq day `
  --lookback-bars 60 `
  --vol-lookback-bars 20 `
  --horizons 5,10,20,60
```

Output artifacts:

- `panel_dataset.csv`
- `summary.json`

Current dataset contents:

- `timestamp`
- `symbol`
- universe metadata columns
- engineered feature columns prefixed with `feature_`
- multi-horizon targets:
  - `target_log_return_h*`
  - `target_direction_h*`

This is the scaffold for:

- global boosted models
- local-vs-global model comparisons
- future multivariate / panel forecasting experiments

## Momentum-Fit Universes

For the current momentum / trend sleeve, do not default mentally to `SPY` as the main proving ground.

Use these as first-class momentum presets instead:

### `momentum_macro`

- `GLD`
- `SLV`
- `TLT`
- `IEF`
- `SPY`
- `QQQ`
- `IWM`
- `DIA`

Interpretation:

- macro / rates / metals are the primary candidates
- equity ETFs remain useful as controls and comparison instruments

### `momentum_crypto`

- `BTC/USD`
- `ETH/USD`
- `SOL/USD`
- `AVAX/USD`

Interpretation:

- crypto is a legitimate momentum candidate
- but it comes with extra venue, funding, and market-structure risk
- use it as a dedicated momentum research bucket, not as an afterthought

### Example Commands

Macro preset:

```powershell
$env:PYTHONPATH="src"
python -m securities_analysis `
  --cfg data\alpaca_keys.cfg `
  panel-dataset `
  --universe-preset momentum_macro `
  --start 2018-01-01 `
  --end 2024-12-31 `
  --freq day `
  --lookback-bars 60 `
  --vol-lookback-bars 20 `
  --horizons 5,10,20,60
```

Crypto preset:

```powershell
$env:PYTHONPATH="src"
python -m securities_analysis `
  --cfg data\alpaca_keys.cfg `
  panel-dataset `
  --universe-preset momentum_crypto `
  --start 2021-01-01 `
  --end 2024-12-31 `
  --freq day `
  --lookback-bars 60 `
  --vol-lookback-bars 20 `
  --horizons 5,10,20,60
```

## Futures Direction

The momentum sleeve should now be thought of as a futures-first research program.

Why:

- the strongest evidence base for time-series momentum / trend is in futures
- especially rates, equity index, and commodity futures
- current ETF proxies are useful bridge instruments, but not the ideal final research universe

### Near-Term Bridge Instruments

Use these ETF proxies when we need accessible macro exposures inside the current stack:

- `TLT`
- `IEF`
- `GLD`
- `SLV`

Interpretation:

- these are macro / futures-like stand-ins
- not the final target venue

### First Futures We Should Support

As the data layer evolves, prioritize:

- US Treasury futures
- S&P 500 futures
- Nasdaq futures
- gold futures
- crude oil futures

### First Futures Research Preset

The repo now supports an initial `momentum_futures` research preset using Yahoo continuous futures symbols:

- `ES=F` : S&P 500 futures proxy
- `NQ=F` : Nasdaq futures proxy
- `ZN=F` : 10-year Treasury futures proxy
- `ZB=F` : 30-year Treasury futures proxy
- `GC=F` : gold futures proxy
- `CL=F` : crude oil futures proxy

Use this for research with:

```powershell
$env:PYTHONPATH="src"
python -m securities_analysis `
  panel-dataset `
  --universe-preset momentum_futures `
  --history-provider yfinance `
  --start 2004-01-01 `
  --end 2024-12-31 `
  --freq day `
  --lookback-bars 60 `
  --vol-lookback-bars 20 `
  --horizons 5,10,20,60
```

Important caveat:

- this is a research bridge using Yahoo's futures symbols
- it is not yet a fully specified continuous-contract engine with explicit roll methodology
- treat it as the first futures-native step, not the final institutional-grade implementation

### Futures Research Requirements

Before futures-native momentum research is trustworthy, we need:

- deeper historical data than the current Alpaca ETF path
- continuous-contract construction
- explicit roll methodology
- contract metadata and expiry handling

### Working Rule

When discussing momentum research:

- do not default back to `SPY`
- default to macro / futures-like exposures first
- treat equity ETFs mainly as controls unless evidence clearly says otherwise
