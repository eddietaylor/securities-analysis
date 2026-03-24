# Forecasting Reference Notes

## Primary Reference

- `docs/references/Mastering_Modern_Time_Series_Forecasting___A_Comprehensive_Guide_to_Statistical__Machine_Learning__and_Deep_Learning_Models_in_Python_18_February_2026.pdf`
- author: Valery Manokhin
- role in this repo: primary forecasting reference for model design, evaluation discipline, feature engineering, and model-family selection

## Secondary Reference

- `docs/references/GPT Deep Research Multi-horizon Forecasting for Algorithmic Trading.pdf`
- role in this repo: concise synthesis of practical multi-horizon forecasting design choices specifically for trading systems

Why it matters:

- it reinforces several directions we were already moving toward
- it is more explicit about direct multi-horizon learning, probabilistic evaluation, and leakage control in trading workflows
- it sharpens the transition point from linear baselines to stronger nonlinear tabular models

## Why This Book Matters For This Project

This repo is no longer only a trading bot prototype. It is becoming a forecasting and decision system with:

- forecasting layers
- conservative risk sizing
- benchmark-aware backtesting
- strategy-family comparison
- experiment tracking

That means the most useful forecasting reference is not just one that teaches models. It also needs to help answer:

- when a series is forecastable at all
- what accuracy and uncertainty metrics to use
- how to validate time series models honestly
- how to engineer multiscale and multivariate features
- which model families are actually worth trying

This book is strong on exactly those questions.

## High-Level Structure

The book is organized in a practical sequence:

1. forecastability and limits
2. forecasting metrics
3. classical baselines
4. robust evaluation
5. feature engineering
6. machine learning
7. deep learning
8. transformers and critical benchmarking

For our purposes, that is a very good order. It pushes us to ask whether a signal is forecastable before overbuilding models.

## Priority Chapters For Our Project

### Tier 1: Read and apply immediately

#### Chapter 2: Forecastability of Time Series

Why it matters:

- helps us avoid wasting time on near-random targets
- gives diagnostics for whether a series or transformed series has usable structure
- directly relevant to trading because raw returns may be weakly forecastable while volatility or decomposed components may be more forecastable

Most relevant topics:

- autocorrelation and partial autocorrelation as first-pass diagnostics
- variance ratio:
  - `VR < 1` mean reversion
  - `VR > 1` trend / persistence
- entropy-based diagnostics
- ForeCA for multivariate forecastability
- mode decomposition ideas like EMD and VMD
- forecast horizon limits and the idea that some targets are only forecastable briefly

Project takeaway:

- before building any serious forecaster, we should add a forecastability screening step for targets and instruments
- we should consider forecasting transformed targets, not just raw price returns

#### Chapter 3: Forecasting Metrics

Why it matters:

- we need a forecasting metric layer that is separate from trading PnL metrics
- the current system is stronger on trading performance metrics than model-forecast metrics

Most relevant topics:

- point forecast metrics
- scale-independent metrics
- forecast value added
- probabilistic forecast metrics:
  - quantile loss / pinball loss
  - interval and distributional scoring
- aggregation across multiple horizons and multiple series

Project takeaway:

- once we move from binary signal rules to explicit forecasts, we should score:
  - direction accuracy
  - magnitude error
  - calibration / interval quality when we add uncertainty estimates

#### Chapter 6: State-of-the-Art Performance Evaluation

Why it matters:

- this chapter is directly aligned with what we already learned the hard way: avoid over-trusting one pretty backtest

Most relevant topics:

- forecast stability
- drift detection
- walk-forward validation
- blocked cross-validation
- purging and embargoing for dependent data
- model comparison tests

Project takeaway:

- this should shape our research process as much as the model chapters do
- for trading data, purged and embargoed validation is especially relevant once labels overlap in time

#### Chapter 7: Feature Engineering for Time Series Forecasting

Why it matters:

- likely the single most actionable chapter for our next modeling step
- our next forecaster should be feature-driven and multiscale, not just a sign on one momentum statistic

Most relevant topics:

- rolling and window-based features
- lag features
- differencing
- autocorrelation features
- spectral and wavelet features
- regime detection and subsequence clustering
- entropy / complexity features
- decomposition-based features
- multivariate and causality-aware features:
  - cross-correlation
  - mutual information
  - cointegration
  - Granger causality
  - transfer entropy
- forecast horizon strategies and feature engineering

Project takeaway:

- this chapter should guide the first serious multi-horizon forecaster
- it is especially relevant to your goal of eventually feeding in many variables

### Tier 2: Important after the next forecaster exists

#### Chapter 8: Advanced Machine Learning for Time Series Forecasting

Why it matters:

- likely the highest-ROI first ML chapter for us
- the book appears favorable to strong feature engineering plus ML rather than blindly jumping to large deep models

Most relevant topics:

- information-theoretic lag selection
- multiscale feature construction
- leakage prevention
- gradient boosting for time series
- global ML models across many series
- failure modes of GBDTs

Project takeaway:

- a feature-rich gradient boosting model is a strong candidate for our first serious non-classical forecaster
- especially for:
  - tabular multivariate features
  - moderate data volumes
  - fast iteration
  - interpretability relative to deep learning

#### Chapter 9: Deep Learning for Time Series Forecasting

Why it matters:

- useful later, but not where I would start next
- the book’s own comparison sections reinforce that deep learning is not automatically superior

Most relevant topics for later:

- DeepAR and DeepState
- N-BEATS / N-HiTS
- DLinear
- TSMixer / TimeMixer
- multivariate MLP-style models
- hybrid classical + neural models

Project takeaway:

- the first deep models we should consider are probably:
  - N-BEATS / N-HiTS for strong univariate or multi-horizon baselines
  - DLinear / TimeMixer / TSMixer for efficient multivariate forecasting
- not generic LSTMs by default

### Tier 3: Useful reference, not immediate priority

#### Chapter 4 and Chapter 5: ARIMA and ETS / Exponential Smoothing

Why they matter:

- essential baselines
- good for sanity checks
- helpful for decomposition intuition

But:

- not the main place I would spend innovation time next

We should still use them as:

- benchmark baselines
- residual-model components
- pieces inside hybrid systems if needed

#### Chapter 10: Transformers for Time Series Forecasting

Why it matters:

- mainly as a warning against hype
- the book appears skeptical and benchmark-oriented here, which is healthy

Project takeaway:

- do not jump to transformers early
- if we ever go there, do it only after strong simpler baselines exist

## What The Book Seems To Say That Fits Our Direction

These points line up very well with the direction of this repo:

- not all series are worth forecasting
- forecastability should be measured before heroic modeling
- strong baselines matter
- validation discipline matters
- leakage control is mandatory
- feature engineering is often the real edge in practical forecasting
- simpler models often beat fancier ones
- multivariate and multi-horizon forecasting should be data-driven, not hype-driven

## What The GPT Deep Research Report Added

The report is not replacing the main textbook, but it did sharpen the practical roadmap.

Most useful additions:

1. direct multi-horizon forecasting should be preferred over vague single-score heuristics
2. gradient-boosted trees are a very strong next nonlinear baseline for engineered tabular features
3. sequence models belong later, after tabular nonlinear baselines
4. probabilistic evaluation and later conformal layers should be part of the design target
5. horizon choice should be discovered empirically
6. trading validation must respect overlapping labels, purging, embargo, and multiple-testing discipline

Practical repo implication:

- we should keep `feature_linear_forecast` as the benchmark baseline
- then test `feature_boosted_forecast`
- then only later move toward heavier sequence models such as TCN / PatchTST / TFT-style families if simpler models justify the complexity

It also reinforced that the evaluation stack should eventually include:

- purged / embargoed split logic
- probabilistic forecast scoring
- PBO / Deflated Sharpe when model search becomes broad

## What We Should Pull Into The Project Soon

### Immediate additions to our modeling doctrine

1. Forecast the right target
- raw returns may be weak
- transformed targets may be stronger:
  - multi-horizon returns
  - volatility
  - trend component
  - regime state

2. Score forecastability before committing
- add diagnostics such as:
  - autocorrelation profile
  - variance ratio
  - entropy / complexity proxies
  - perhaps later multivariate forecastability measures

3. Separate forecasting metrics from trading metrics
- forecast quality should be evaluated before it is translated into positions

4. Use walk-forward evaluation as default
- later add purging / embargo when label overlap makes it necessary

5. Favor interpretable multiscale features for the next model
- not deep black-box models yet

## Recommended Next Model Path

### Immediate build target: a multi-horizon forecast model

The next model should not be just “stronger momentum.”
It should be an explicit forecast module with:

- multiple horizons
- multiscale features
- optional multivariate inputs
- forecast output separated from execution and risk

### Proposed MVP design

Target:

- predict future log return over multiple horizons
  - e.g. `1`, `5`, `10`, `20` bars

Feature families:

- lagged returns
- rolling means
- rolling vol
- rolling drawdown-like state variables
- short / medium / long horizon momentum
- ratio features across horizons
- maybe simple realized-vol and range-based features

Model family:

- first: structured linear / weighted forecast combination or tree-based model
- not deep learning first

Why:

- faster iteration
- easier validation
- easier interpretation
- more aligned with our current platform and data volume

### Forecast output

The model should output something like:

- horizon forecasts
- aggregate directional score
- confidence or uncertainty proxy
- forecast diagnostics

Risk should still decide:

- whether to act
- how much to size

## Probabilistic Forecasting and Conformal Prediction

The book chapters we scanned emphasize probabilistic metrics, but not a dedicated conformal workflow.

Your idea still makes sense.

Planned stance:

- do not block the next model on conformal prediction
- but design the forecast interface so uncertainty bands can be added later

Concretely:

- build deterministic multi-horizon forecasts first
- later add:
  - quantile forecasts
  - conformal intervals
  - calibration diagnostics

That gives us a practical sequence:

1. better point forecasts
2. better uncertainty
3. better decision rules from both

## Recommended Reading Order For Us

1. Chapter 2
2. Chapter 3
3. Chapter 6
4. Chapter 7
5. Chapter 8
6. selected parts of Chapter 9
7. selected parts of Chapter 10 only for perspective

## Concrete Repo Follow-Up

These notes should drive the next implementation steps:

1. add a forecasting roadmap note to the journal
2. build a multi-horizon forecast interface
3. implement a first multiscale forecaster
4. add forecast-quality metrics to the research harness
5. later add multivariate covariates and conformal uncertainty

## Future Architecture Note

The project should keep researching the shared multi-instrument forecasting architecture that is currently producing the strongest momentum sleeve.

Important distinction:

- it is not a true joint multi-output model
- but it is more than a purely local per-symbol model

Current winning form:

- one shared model
- many instruments in the universe
- one forecast target per row
- multivariate inputs and repeated walk-forward retraining

This architecture is worth continuing to study because it may be a practical middle ground between:

- tiny local models with too little data
- and much more complex fully joint sequence models

## Future Decision Layer Note

The project should also treat `forecasting` and `decision-making` as separate research problems.

Current decision layer is simple:

- rank forecasts
- pick top names
- rebalance on a fixed schedule

This is a good baseline, but not necessarily the best use of the forecasts.

Future decision-layer research ideas:

- optimize allocations using:
  - forecast mean
  - forecast uncertainty
  - turnover cost
  - diversification structure
  - risk constraints
- compare fixed rules against explicit decision optimization
- later explore RL-like long-horizon reward optimization only after:
  - strong benchmark decision rules exist
  - uncertainty estimates are credible
  - validation discipline for policy learning is well defined

## GPT Deep Research: Feature Engineering And Selection

Reference:

- `docs/references/GPT Deep Research Feature Engineering and Selection for Algorithmic Trading Strategies.pdf`

Most important takeaway:

- feature engineering should be explicitly tied to:
  - the strategy's economic mechanism
  - the operating horizon
  - the execution and cost model

This strongly supports a layered feature pipeline rather than one generic bag of indicators.

### What The Report Reinforces

- `momentum / trend` at daily-to-monthly horizons should be built mainly from:
  - multi-horizon return aggregation
  - relative strength
  - volatility scaling
  - trend slope / crossover / breakout structure
  - liquidity and cost controls
  - macro regime filters
- `mean reversion` should emphasize:
  - z-scored deviations
  - short-term reversal structure
  - volatility regime
  - event / news gates
  - and, for intraday work, microstructure features
- validation and selection discipline matter as much as the features:
  - causal construction only
  - purged / embargoed validation when labels overlap
  - avoid feature mining by endless variant search
- transaction costs should be treated as part of feature design:
  - spread, liquidity, and impact proxies are not optional filters

### Implication For This Repo

Our current forecasting features are still mostly:

- self-derived from each instrument's own price history
- plus a small amount of cross-asset context
- plus a few hand-coded regime flags

That is a reasonable first generation, but it is not yet a real feature engineering pipeline.

### Proposed Feature Pipeline Layers

#### Layer 1: Core Price-State Features

Keep and expand the current base:

- multi-horizon cumulative returns
- skip-period momentum such as `12-1` style constructions where relevant
- realized volatility and volatility ratios
- moving-average spreads, slopes, and crossover strength
- breakout / range position features
- drawdown and distance-from-extremes state

Why:

- this is still the core of the current futures momentum sleeve
- the report reinforces that these should remain the foundation

#### Layer 2: Cross-Asset And Relative Features

Add more explicit relative-state features:

- relative strength versus benchmark or peer group
- residual momentum after controlling for broad factors
- rolling correlation / correlation-regime features
- cross-asset confirmation or disagreement signals
- market concentration and dispersion measures

Why:

- our current `context_*` features are a start, but still quite shallow
- the report strongly supports cross-asset and relative constructions for momentum and trend

#### Layer 3: Execution / Tradability Features

Add features that model whether the signal is worth trading:

- dollar volume trend
- spread proxies
- impact proxies
- turnover pressure
- liquidity regime indicators

Why:

- the report is very explicit that cost-aware features can be core, not decorative
- this matters especially if we later expand beyond daily ETF work

#### Layer 4: Macro And Regime Features

Move beyond hand-coded event flags:

- rates level and slope proxies
- inflation / growth / policy surprise proxies
- commodity and dollar regime features
- volatility regime features
- stress / flight-to-safety state proxies

Why:

- the report repeatedly frames macro regime as an important secondary filter for momentum / trend
- this is especially relevant to our futures-first sleeve

#### Layer 5: Event Features

Add explicit event-state columns with causal lags:

- scheduled macro release windows
- earnings windows for equity mean reversion work
- event embargo flags
- post-event decay features

Why:

- the report treats event filters as especially important for mean reversion and breakouts
- this is a safer early exogenous-data layer than jumping straight to raw text

#### Layer 6: Textual / Fundamental Exogenous Features

This is where ideas like `10-K`, `10-Q`, and news sentiment belong.

Candidate additions:

- lagged news sentiment
- sentiment surprise versus trailing baseline
- filing sentiment / topic flags
- filing recency
- earnings-call or company-news shock features

Important caution:

- these must be timestamp-aligned to what was truly knowable at decision time
- they are more natural for equity and cross-sectional sleeves than for the current futures momentum sleeve
- they should be added only after the structured market-state pipeline is solid

### Priority Sequencing

Best near-term build order:

1. strengthen structured price-state features
2. add richer cross-asset / relative features
3. add tradability and liquidity features
4. add macro-regime features
5. add event features
6. only then add textual / filings features

This sequence is important because:

- it captures most of the report's highest-confidence recommendations first
- it keeps the pipeline auditable
- it avoids rushing into sparse and leakage-prone text data before the structured baseline is strong

### Strategy-Specific Guidance

For the current `futures momentum` sleeve:

- prioritize:
  - return aggregation
  - volatility scaling
  - breakout / trend structure
  - relative strength
  - liquidity / cost filters
  - macro-regime features
- deprioritize for now:
  - `10-K`
  - company filings
  - company news sentiment

For the `equity mean reversion` sleeve:

- prioritize:
  - z-scored deviations
  - reversal / snapback state
  - event filters
  - market / sector context
  - eventually news and company-level textual features

This is the key distinction:

- `10-K` and company-news features are promising
- but they are much more likely to help the equity sleeve than the futures momentum sleeve

### Concrete Repo Follow-Up

The repo should evolve toward a real feature pipeline with:

1. feature families registered separately
2. strategy-specific feature presets
3. explicit causal lag rules for every exogenous source
4. feature-store style joins by timestamp and symbol
5. ablation testing by feature family, not just by individual column

If we do this well, the system will stop being:

- a forecasting model with a handful of hand-written indicators

and start becoming:

- a genuine research platform for structured, multi-source, strategy-aware feature engineering
