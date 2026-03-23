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

## 2026-03-23 - Sleeve Portfolio Framing

The project is no longer just searching for one strategy to beat `SPY` outright.

It is now explicitly searching for multiple sleeves that may later be combined into a stronger total portfolio.

### What We Now Have

- a first credible `momentum / trend` sleeve candidate in futures-style instruments
- evidence that this sleeve can improve a blended `SPY + sleeve` portfolio even though it does not yet beat `SPY` standalone

### What This Changes

We should now search for the `next` sleeve rather than asking the momentum sleeve to do everything.

Current lane split:

- `momentum / trend`:
  - continue in futures
  - maintain the existing forecastability -> shortlist -> forecast -> backtest funnel
- `mean reversion`:
  - begin as a second research lane
  - start in liquid equity / sector ETFs where the strategy-instrument fit is more natural

### First Mean Reversion Universe

The codebase now has a `mean_reversion_equity` universe preset built around:

- `SPY, QQQ, IWM, DIA`
- `XLK, XLF, XLE, XLU, XLI, XLP, XLV`
- `SMH`

### Mean Reversion Doctrine

- search shorter horizons first
- prefer structure consistent with snapback rather than persistence
- judge the sleeve both:
  - standalone
  - and as a diversifier against `SPY` and the futures momentum sleeve

### Explicit To-Dos

- continue refining the first futures momentum sleeve
- continue refining the first equity mean-reversion sleeve
- maintain a `winner board` for each sleeve family so the best:
  - instruments
  - horizons
  - model families
  - trading-shell variants
  stay visible across sessions

Broad-search to-dos:

- eventually sweep across the broad futures universe for the momentum sleeve, not just the current shortlist
- eventually sweep across a much broader liquid equity / sector / thematic ETF universe for the mean-reversion sleeve
- treat current shortlists as staging filters, not as the final universe boundary
- assume there may still be important instruments we are missing until the broad sweeps are done

### Architecture To-Do

Keep researching the current shared multi-instrument forecasting architecture.

Current winner uses:

- one shared forecaster
- many instruments
- one target horizon per run
- repeated walk-forward retraining

That architecture is now a real research object in its own right and should not be discarded just because it is not a true joint multi-output model.

Future exploration paths:

- compare shared single-target forecasters against more explicitly multi-output architectures
- compare shared forecasters against per-instrument models where sample size allows
- keep separating:
  - `forecast model quality`
  - `decision rule quality`

### Decision Layer To-Do

The current trading shell is still simple:

- rank forecasts
- take the top `k`
- rebalance on a fixed cadence

That is useful as a baseline, but it is not the end state.

Future decision-layer research should include:

- optimization over forecast and uncertainty jointly
- portfolio construction that explicitly trades off:
  - expected return
  - uncertainty
  - turnover
  - diversification
  - drawdown control
- longer-term reward optimization rather than one fixed local rule

Possible future avenue:

- a decision optimizer that consumes forecasts plus uncertainty and learns a policy for long-term reward
- potentially RL-like, but only after we have strong benchmark decision rules and careful validation discipline

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

## 2026-03-22 - Antifragile Architecture Framing

Recent discussion sharpened an important distinction:

- our current system is developing `robustness hygiene`
- it is not yet genuinely `antifragile`

That is fine. The immediate job is not to pretend we already have an antifragile trading business. The immediate job is to build toward that architecture in the right order.

### Core Layering

We should think about the future stack in six layers:

1. `signal engines`
- forecasting sleeves that generate edge candidates
- examples:
  - trend / momentum
  - breakout / compression-expansion
  - mean reversion
  - later, relative value or event-driven sleeves

2. `uncertainty engine`
- estimates how much we trust the forecast itself
- examples:
  - ensemble disagreement
  - conformal intervals later
  - out-of-distribution / drift scores
  - residual instability

3. `state engine`
- tracks continuous market structure variables rather than brittle hard-coded regimes
- examples:
  - realized volatility
  - vol-of-vol
  - cross-asset / cross-sleeve correlation
  - dispersion
  - liquidity / spread stress
  - model residual stress

4. `allocator`
- distributes capital across sleeves based on:
  - expected edge
  - uncertainty
  - diversification value
  - recent degradation and stress behavior

5. `survival layer`
- overrides everything when needed
- examples:
  - gross / net limits
  - drawdown throttles
  - concentration caps
  - spread / slippage guards
  - kill switches

6. `exploration engine`
- small controlled budget for discovering new sleeves, instruments, or feature families without destabilizing the core book

### What We Already Have

- early `signal engine` infrastructure
- an early `survival layer`
- benchmark-aware research
- experiment tracking
- trading dashboard and forecast dashboard
- glass-box validation notebooks

### What We Do Not Yet Have

- a real `uncertainty engine`
- a first-class `state engine`
- a portfolio-level `allocator`
- a deliberate `exploration engine`
- any credible convex / crisis-opportunistic sleeve

### Current Priority Order

Do not jump straight to allocator complexity before the sleeves themselves are credible.

Priority:

1. improve forecast quality of individual sleeves
2. validate sleeves internally and against benchmarks
3. add uncertainty-aware sizing / trust penalties
4. promote continuous state variables into a first-class engine
5. build sleeve allocation logic
6. later add crisis-sensitive / convex sleeves

### Doctrine Update

- keep `survival` separate from `alpha`
- do not loosen risk controls just because a weak forecast looks promising in one backtest
- use market stress as information eventually, but first build sleeves that deserve capital
- aim for `adaptive` first; `antifragile` is the long-term architecture goal, not a label we have earned yet

### Training History Note

For trainable forecast models, we should compare:

- `expanding history`
  - keep all past training observations
- `rolling history`
  - retain only the most recent `N` observations

Rationale:
- more years can help with sample size and regime coverage
- too much stale history can poison the learner if market structure shifts

Implementation note:
- trainable forecast strategies now support a `max_train_samples` control
- `0` / `None` means expanding history
- positive values allow rolling-history experiments without changing the walk-forward validation logic

## 2026-03-22 - Boosting, Data-Driven Horizons, and Overlap-Aware Validation

We moved the forecasting stack one level up from “linear-only baseline” to “first nonlinear candidate plus stricter diagnostics.”

### What Changed

- installed `scikit-learn` and added a first boosted multi-horizon strategy family:
  - `feature_boosted_forecast`
- added a shared richer forecasting feature pack including:
  - multi-scale returns
  - multi-scale volatility
  - MA spread and slope
  - drawdown depth and duration
  - days since rolling high / low
  - compression and breakout-style features
  - sign-consistency features
  - calendar time embeddings
- added data-driven horizon selection inside the boosted strategy:
  - candidate horizons are scored from prior out-of-sample forecast quality
  - the active short / medium / long horizons are chosen from that history rather than hard-coded forever
- upgraded forecast diagnostics with overlap-aware reporting:
  - per-horizon purged observations
  - purged correlation
  - purged MAE / RMSE
  - purged directional accuracy
  - recommended horizons summary
- updated the forecast dashboard to show:
  - validation method details
  - recommended horizons
  - boosted-model feature-importance summaries

### Why This Matters

This is the first time the repo explicitly treats three ideas as first-class:

1. nonlinear forecasting models are part of the roadmap now, not just a future idea
2. horizon choice should be empirical, not folklore
3. overlapping horizon labels can flatter diagnostics if we are careless

### First Result

The first `feature_boosted_forecast` run on `SPY 2024` with a `252`-sample rolling window did **not** beat the current linear baseline.

Checkpoint:

- cumulative return: about `-1.65%`
- Sharpe: about `-0.88`
- max drawdown: about `-2.55%`

Diagnostics note:

- overlapping correlations looked modestly positive on some horizons
- purged metrics were materially harsher
- that is exactly the behavior we wanted from the stricter validation layer

### Current Interpretation

- boosted trees are still the right next model family to test
- but the first boosted formulation is not yet better than the linear baseline
- this is not failure; it is useful evidence
- the stricter validation is doing its job by preventing us from over-reading weak overlapping-label results

### Updated Modeling Doctrine

Current benchmark order:

1. `feature_linear_forecast`
2. `feature_boosted_forecast`
3. only later sequence / deep models if simpler nonlinear models justify it

Current horizon doctrine:

- start with a candidate horizon grid
- score horizons by purged forecast quality
- prefer stable horizons over one-sample winners

Current validation doctrine:

- keep rolling-origin walk-forward as the backbone
- add overlap-aware purged reporting for multi-horizon targets
- later, when model search broadens, add purging / embargo directly into split construction and bring in multiple-testing controls such as PBO / Deflated Sharpe

## 2026-03-22 - Universe Design Became First-Class

If we move toward panel-style forecasting, the universe is part of the model design, not just a list of tickers.

### Why This Matters

The forecasting model should not be asked to learn from:

- a tiny universe with too few samples
- a huge random universe with incompatible instruments
- illiquid names that make backtests unrealistic
- symbols with unstable or short histories

Universe design affects:

- data volume
- model generalization
- execution realism
- whether panel-style ML is even sensible

### First Panel-Training Universe Direction

Start with a curated liquid ETF universe rather than single stocks or an unconstrained market scrape.

First candidate groups:

- broad equity index ETFs:
  - `SPY`
  - `QQQ`
  - `IWM`
  - `DIA`
- rates / fixed income proxies:
  - `TLT`
  - `IEF`
- metals / commodity proxies:
  - `GLD`
  - `SLV`
- liquid sector ETFs:
  - `XLK`
  - `XLF`
  - `XLE`
  - `XLU`
- international / macro extensions later:
  - `EEM`
  - `FXI`

This is not the forever universe. It is the first sane hunting ground for panel forecasting.

### Hard Universe Filters

Any instrument admitted to the panel-training universe should meet:

- sufficient clean history
- strong average dollar volume
- reasonable spreads
- tradability in our current broker / execution setup
- stable enough product design to avoid pathological artifacts

### Metadata Doctrine

The universe should eventually store metadata per symbol such as:

- asset class
- sub-class / theme
- sector
- volatility bucket
- liquidity bucket

This matters because panel models should know when they are looking at different kinds of instruments.

### Modeling Doctrine Update

Do not treat panel training as:

- “throw every symbol into one model and hope”

Treat it as:

- define a sane, liquid, diverse universe
- tag it with useful metadata
- then test whether global models learn transferable structure across that universe

### Near-Term Plan

1. formalize the first panel-training universe in the runbook
2. build a panel dataset builder over that universe
3. compare local per-symbol models vs global panel-style models
4. only after that build a broader forecastability search layer

## 2026-03-22 - Momentum Universe Pivot

Recent external research sharpened an important point:

- `SPY` should remain a benchmark and control instrument
- it should not remain the center of gravity for momentum research

### Momentum-Fit Doctrine

For the current time-series momentum / trend sleeve, the better proving grounds are:

- futures in the ideal long-term setup
- macro / commodity / rates proxies in the current Alpaca-accessible setup
- crypto as a legitimate momentum candidate, with the caveat that it brings extra venue and market-structure risk

### Practical Implication For This Repo

Near-term momentum research should prioritize:

- macro ETF proxies:
  - `GLD`
  - `SLV`
  - `TLT`
  - `IEF`
- crypto spot:
  - `BTC/USD`
  - `ETH/USD`
  - `SOL/USD`
  - `AVAX/USD`

Control / comparison instruments can still include:

- `SPY`
- `QQQ`
- `IWM`
- `DIA`

But those should be interpreted as:

- controls
- benchmarks
- or later candidates for cross-sectional / rotation logic

not the primary place we expect a clean standalone momentum edge.

### Implementation Note

The panel dataset builder now supports named universe presets so this doctrine is executable rather than just aspirational:

- `panel_default`
- `momentum_macro`
- `momentum_crypto`

## 2026-03-22 - Futures Road

We are explicitly choosing to move the momentum research program toward futures and futures-like macro exposures.

### Why

The external instrument/strategy report sharpened something important:

- time-series momentum / trend following is best evidenced in futures
- especially:
  - equity index futures
  - rates futures
  - commodity futures
  - often currency futures

That means the most natural long-term home for this sleeve is not broad equity ETFs. It is a systematic macro / futures stack.

### Practical Doctrine

Near term:

- continue using ETF proxies where they are the best currently accessible stand-ins
- especially:
  - `TLT`
  - `IEF`
  - `GLD`
  - `SLV`
- treat these as bridge instruments, not the final destination

Medium term:

- add a proper deep-history and research path for actual futures contracts
- target the most canonical momentum-friendly futures first

### First Futures Candidates

Priority contracts / exposures to support:

- rates:
  - US Treasury futures
- equity indices:
  - S&P 500 futures
  - Nasdaq futures
- commodities:
  - gold futures
  - crude oil futures
- later:
  - currency futures

### Engineering Implication

The roadmap should now include:

1. futures-aware historical data loading
2. futures contract normalization / roll handling
3. continuous-contract research series
4. momentum research on futures-native instruments, not just ETF proxies
5. eventually a futures-capable execution path if we want to deploy there

### Immediate To-Do

- keep the current macro ETF proxy research going as the bridge
- but treat the actual futures data path as a first-class next build item

## 2026-03-22 - Deep-History Futures Research Learnings

Today clarified several important things about the momentum sleeve.

### 1. Deep history matters, but not in the naive way

- adding a deep-history loader was necessary
- the project can now build panel datasets from `yfinance` for ETF proxies and futures-style instruments
- this let us move from shallow recent-history experiments to research spanning roughly `2004` onward for many futures symbols

Important nuance:

- more history did not magically make every model good
- it did make the experiments much more honest and much more aligned with the real regime question

### 2. The original boosted baseline was not strong enough

- the first panel boosting work used plain `sklearn` gradient boosting with shallow trees
- that was not a fair representative of modern tabular boosting
- we added a stronger nonlinear benchmark using `CatBoost`

Result:

- even after upgrading to a more serious boosting family, linear ridge remained the strongest overall baseline on the current futures tests
- this points more toward feature / target bottlenecks than toward “boosting is bad”

### 3. Futures do look more natural for momentum than the earlier ETF-centric framing

- moving the research path toward futures was the right decision
- on the first futures-native tests, longer horizons showed more life than short horizons
- this is much more consistent with classic time-series momentum evidence

### 4. Horizon choice should be data-driven

We ran a broad linear horizon sweep over futures and learned that:

- the signal is not strongest at the shortest horizons
- in the initial smaller futures universe, `60/90/120` looked strongest
- after broadening the universe and shortlisting by forecastability, `30/45/120` emerged as especially interesting aggregate horizons

Conclusion:

- horizon should be discovered empirically
- not fixed by folklore

### 5. Forecastability scanning is now a first-class research stage

We added a cheap forecastability scan across a broad futures universe using:

- lag-1 autocorrelation
- variance ratio 5
- variance ratio 20
- spectral entropy

This gave us a model-free ranking of futures contracts before expensive forecasting work.

High-level lesson:

- broad forecastability diagnostics and fitted-model diagnostics are related but not identical
- both are useful filters

### 6. The current best candidates are no longer just the original handpicked macro names

The broad scan and the shortlist sweep surfaced promising contracts in:

- agriculture
- energy
- rates
- metals

Notably useful names included:

- `GC=F`
- `ZB=F`
- `ES=F`
- `RB=F`
- `HO=F`
- `ZC=F`
- `ZS=F`

So the research program should stay broad inside futures rather than collapsing too early to one tiny macro subset.

### 7. Current doctrine after today

- momentum research is futures-first
- ETF proxies are bridges, not the end-state
- model-free forecastability scan should come before expensive model fitting across a broad universe
- linear ridge remains the honest baseline
- CatBoost is the nonlinear benchmark worth keeping
- next model work should focus on the best futures and the empirically strongest horizons
