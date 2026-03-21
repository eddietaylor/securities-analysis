# Progress Journal

## 2026-03-19

### Current State

- resurrected the old repo into package code under `src/securities_analysis/`
- restored Alpaca auth and historical data access
- built a reusable Alpaca execution wrapper and CLI
- added an MVP trend-following strategy with volatility scaling
- added a first risk layer with:
  - fractional Kelly sizing
  - max position and trade notional caps
  - spread filter
  - daily drawdown kill switch
  - flatten-on-zero-exposure logic
- added a backtest engine with transaction cost modeling
- added artifact persistence for backtests
- created an inspection notebook for step-by-step validation
- validated the first SPY 2024 backtest end to end
- fixed a real state bug where flat decisions were not fully reflected in tracked position state
- restored GitHub SSH access and merged the resurrection work into `main`

### What We Learned

- the project was much closer to paper-trading readiness than it felt
- the main missing piece was system architecture, not broker connectivity
- the current MVP is plausible enough to research further, but not yet trustworthy enough to scale capital
- the signal is currently too narrow to support any serious business claim on its own

### Missing Pieces

- stronger backtesting realism
- parameter sweep and robustness testing
- multi-symbol portfolio research
- additional strategy sleeves beyond one long/flat trend model
- experiment tracking and reproducible run summaries
- paper-trading parity checks against backtest assumptions
- monitoring, logging, alerts, and operational discipline
- a proper research cadence and decision journal

### Next Build Focus

1. build a batch research harness for multi-symbol parameter sweeps
2. compare parameter regimes using saved leaderboard artifacts
3. identify whether the current model is under-sized, over-filtered, or both
4. add at least one additional strategy sleeve only after the research loop is trustworthy

### Research Baseline

The first standardized research sweep should use:

- symbols: `SPY, QQQ, IWM, DIA, TLT, GLD`
- frequency: daily
- date range: `2024-01-01` through `2024-12-31`
- ranking metric: `sharpe_ratio`
- saved top-run artifacts for manual inspection

Reference:

- `docs/research_runbook.md`
- `scripts/run_first_research_sweep.ps1`

### Research Doctrine

The objective is not to find one magical instrument or one magical parameter set.

The objective is to build a repeatable process that tells us:

- which strategy sleeve works
- on which instruments
- in which regimes
- with what risk profile
- and whether that edge survives costs and passive benchmarks

Practical implications:

- start with a curated liquid universe, not a tiny fixed watchlist and not the whole market
- test `instrument x strategy sleeve x regime`, not instruments in isolation
- compare every strategy run to:
  - buy-and-hold of the same symbol
  - a market benchmark proxy such as `SPY`
- prefer robustness across multiple periods over one outstanding year
- do not optimize specifically for `GLD`, `SPY`, or any single winner from one sample

Current doctrine:

1. trust the research process more than any single backtest
2. prefer cross-period robustness over peak single-period Sharpe
3. do not add more sleeves until this process is trustworthy

### Operating Note

Do not rely on chat memory alone for project state. This file is the durable source of truth for:

- where the system stands
- what was learned
- what needs to happen next

### Validation Notebook Note

Do not try to build explanation notebooks for every layer all at once.

Instead, add a small set of glass-box validation notebooks at the points where system complexity is starting to outrun intuition.

Immediate priority:

- a single-path walkthrough notebook that shows:
  - bars
  - runtime spec
  - signal decision
  - risk decision
  - order intent
  - final backtest step

Follow-on notebooks can cover:

- backtest accounting and cost attribution
- research harness assembly and leaderboard construction

### Dashboard Note

Backtest inspection should follow a two-layer pattern:

- run explorer:
  - browse tracked runs from the experiment registry
  - filter and compare at a high level
- run detail dashboard:
  - inspect one run deeply
  - review equity, drawdown, turnover, cost drag, trade activity, and rejection events

Do not try to collapse every strategy, instrument, and parameter combination into one giant page.

### Forecasting Roadmap Note

We now have enough platform infrastructure to shift the main bottleneck from plumbing to model quality.

Next forecasting tracks to research:

- richer trend model with multiple horizons
- regime-aware trend model
- volatility forecasting model
- breakout / compression-expansion model

Priority order:

1. multi-horizon forecaster
2. regime-aware extensions to trend
3. breakout / compression-expansion sleeve
4. volatility forecasting as a sizing and gating enhancement

Current stance:

- keep the risk shell conservative for now
- seek alpha from better forecasting, not from simply increasing risk
- favor structured and interpretable forecasting upgrades before jumping to large deep models

Primary forecasting reference:

- `docs/references/Mastering_Modern_Time_Series_Forecasting___A_Comprehensive_Guide_to_Statistical__Machine_Learning__and_Deep_Learning_Models_in_Python_18_February_2026.pdf`
- companion notes: `docs/references/reading_notes.md`

### Multi-Horizon Forecasting Checkpoint

The first forecasting-layer upgrade beyond the original simple trend rule is now underway.

Current implementation direction:

- add a `multi_horizon_trend` strategy family
- expose explicit forecast snapshots and horizon-level components
- keep the existing simple trend and mean-reversion sleeves as baselines

The immediate objective is not to maximize return by taking more risk.
The immediate objective is to improve forecast quality while preserving the conservative risk shell.

First backtest checkpoint:

- `multi_horizon_trend` ran successfully through the standard backtest path on `SPY 2024`
- first result was roughly flat and clearly not a production-quality signal yet
- that is acceptable at this stage because the immediate goal was to prove the forecasting-layer integration, not to declare victory on the first formulation
- next focus should be improving the forecast design and feature set rather than loosening risk controls

Validation note:

- current forecast diagnostics use chronological rolling-origin / walk-forward evaluation
- they do not use shuffled k-fold cross-validation
- this is acceptable for the current online rule-based forecaster because each signal is generated using only past information
- once we introduce fitted ML models, we should upgrade to explicit walk-forward retraining and consider purging / embargo when forecast horizons overlap
## 2026-03-21 - Forecast Validation Became First-Class

We now have a separate forecasting-validation layer in addition to the trading/backtest dashboard layer.

What changed:
- forecast diagnostics are explicitly recorded as chronological rolling-origin / walk-forward evaluation
- the artifact now says this is not shuffled k-fold cross-validation
- per-horizon forecast quality is saved with correlation, MAE, RMSE, bias, and directional accuracy
- lightweight forecastability diagnostics are saved for the underlying asset return stream
- a dedicated walkthrough notebook was added:
  - `notebooks/trading_bots/forecast_validation_walkthrough.ipynb`

Why this matters:
- the current multi-horizon forecaster is not good yet, but now we can see why
- the first SPY run showed weak/negative forecast correlations despite superficially acceptable directional accuracy
- this strongly suggests that sign alone is not enough and the forecast magnitude/construction is wrong

Current doctrine:
- validate forecasting quality before touching the risk shell
- keep using chronological walk-forward evaluation
- when we add fitted ML forecasters later, extend this with explicit walk-forward retraining and potentially purging/embargo for overlapping horizons
