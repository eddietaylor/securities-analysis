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
