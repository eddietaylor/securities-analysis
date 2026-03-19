$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"

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
