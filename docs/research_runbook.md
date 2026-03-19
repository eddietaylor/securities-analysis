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
