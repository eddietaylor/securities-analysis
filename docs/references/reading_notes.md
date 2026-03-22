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
